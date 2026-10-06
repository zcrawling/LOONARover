"""Whole-connectome simulation. No replacement network or heuristic motor fallback.

Recurrent neurons, equations, weights, delays and connectivity come directly
from upstream create_model(). Added Poisson afferents are an artificial sensory
interface, not a reconstruction of a retina or the fly's mechanosensation.
"""

import importlib.util
from pathlib import Path
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
POPULATIONS = ("LC4", "LPLC2", "DNp09", "DNa01", "DNa02")


class WholeBrain:
    def __init__(self, seed=1, motivation_hz=0.0):
        import brian2 as b
        import pandas as pd

        from .provenance import verify
        verify()
        if not np.isfinite(motivation_hz) or not 0 <= motivation_hz <= 150:
            raise ValueError("motivation_hz must be in [0, 150]")
        self.b = b
        self.motivation_hz = float(motivation_hz)
        b.start_scope()
        b.seed(seed)
        b.defaultclock.dt = 0.1 * b.ms
        (ROOT / "cache/cython").mkdir(parents=True, exist_ok=True)
        b.prefs.codegen.runtime.cython.cache_dir = str(ROOT / "cache/cython")
        source = ROOT / "vendor/fly-brain/code/paper-phil-drosophila/model.py"
        spec = importlib.util.spec_from_file_location("upstream_shiu_model", source)
        upstream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(upstream)
        data = ROOT / "vendor/fly-brain/data"
        ids = pd.read_csv(data / "2025_Completeness_783.csv", index_col=0).index
        annotation = pd.read_csv(ROOT / "vendor/neuron_annotations.tsv", sep="\t",
                                 usecols=["root_id", "cell_type", "side"])
        annotation = annotation[annotation.root_id.isin(ids)]
        if annotation.root_id.duplicated().any():
            raise ValueError("duplicate neuron annotation IDs")
        self.populations = {}
        self.root_ids = {}
        for name in POPULATIONS:
            for side in ("left", "right"):
                key = f"{name}_{side}"
                selected = annotation[(annotation.cell_type == name) & (annotation.side == side)]
                if selected.empty or (name.startswith("DN") and len(selected) != 1):
                    raise ValueError(f"Missing/ambiguous exact cell_type and side: {key}")
                self.root_ids[key] = [int(x) for x in selected.root_id]
                self.populations[key] = ids.get_indexer(selected.root_id)
        self.params = upstream.default_params.copy()
        self.neurons, self.synapses, self.original_monitor = upstream.create_model(
            data / "2025_Completeness_783.csv", data / "2025_Connectivity_783.parquet", self.params)
        # Only counters are retained. The upstream full spike-train monitor is
        # deliberately excluded from the streaming Network to bound memory.
        self.monitor = b.SpikeMonitor(self.neurons, record=False, name="body_counts")
        self.input_keys = [f"{name}_{side}" for name in ("LC4", "LPLC2", "DNp09")
                           for side in ("left", "right")]
        targets = np.concatenate([self.populations[k] for k in self.input_keys])
        self.input_slices = {}
        offset = 0
        for key in self.input_keys:
            size = len(self.populations[key])
            self.input_slices[key] = slice(offset, offset + size)
            offset += size
        # Independent, dynamically adjustable Poisson sources. The injection
        # amplitude and zero refractory period of stimulated cells match poi()
        # in upstream; the dynamic rate encoder below is our own adapter.
        self.sources = b.PoissonGroup(len(targets), rates=0*b.Hz, name="body_afferents")
        self.afferents = b.Synapses(self.sources, self.neurons,
            on_pre="v_post += stimulus", namespace={"stimulus": self.params["w_syn"] * self.params["f_poi"]},
            name="body_input_synapses")
        self.afferents.connect(i=np.arange(len(targets)), j=targets)
        self.neurons.rfc[targets] = 0*b.ms
        self.network = b.Network(self.neurons, self.synapses, self.monitor, self.sources, self.afferents)
        self.previous_counts = np.zeros(len(ids), dtype=np.int64)
        self.smoothed = {key: 0.0 for key in self.populations}
        self.neuron_count = len(ids)
        self.connection_count = len(self.synapses)

    def step(self, rates, duration_ms=10.0):
        if not np.isfinite(duration_ms) or not 0 < duration_ms <= 1000:
            raise ValueError("invalid simulated duration")
        self.set_rates(rates)
        start = time.monotonic()
        self.network.run(duration_ms * self.b.ms, namespace={})
        return self.read_counts(duration_ms, time.monotonic() - start)

    def set_rates(self, rates):
        if any(key not in self.input_slices for key in rates):
            raise ValueError("unknown input population")
        source_rates = np.zeros(len(self.sources))
        for key, indices in self.input_slices.items():
            rate = rates.get(key, self.motivation_hz if key.startswith("DNp09") else 0.0)
            if not np.isfinite(rate) or not 0 <= rate <= 150:
                raise ValueError(f"invalid Poisson rate for {key}")
            source_rates[indices] = rate
        self.sources.rates = source_rates * self.b.Hz

    def read_counts(self, duration_ms, elapsed):
        counts = np.asarray(self.monitor.count[:], dtype=np.int64)
        delta = counts - self.previous_counts
        self.previous_counts = counts.copy()
        hz = {key: float(np.mean(delta[indices]) * 1000 / duration_ms)
              for key, indices in self.populations.items()}
        # Smoothing is in simulated time, not wall time; both clocks are exposed.
        alpha = 1.0 - np.exp(-duration_ms / 100.0)
        for key, value in hz.items():
            self.smoothed[key] += alpha * (value - self.smoothed[key])
        return {"population_hz": hz, "smoothed_hz": self.smoothed.copy(),
                "spikes": int(delta.sum()), "simulated_ms": duration_ms,
                "brain_time_ms": float(self.network.t / self.b.ms),
                "compute_ms": elapsed * 1000, "wall_per_brain": elapsed * 1000 / duration_ms}

    def stream(self, next_input, on_result, should_stop, duration_ms=10.0):
        """One continuous Brian run, rate changes at exact neural boundaries.

        Avoids re-preparing a 15-million-edge spike queue per 10 ms window.
        next_input returns (opaque request, rates) or None. Missing requests
        remove ALL external drive, including optional P9 positive control;
        recurrent dynamics continue, but no stale request produces a result.
        """
        if not np.isfinite(duration_ms) or not 1 <= duration_ms <= 50:
            raise ValueError("stream duration must be 1..50 ms")
        active = None
        started = None

        def boundary():
            nonlocal active, started
            if should_stop():
                self.network.stop()
                return
            if started is not None:
                result = self.read_counts(duration_ms, time.monotonic() - started)
                if active is not None:
                    on_result(active[0], result)
            active = next_input()
            if should_stop():
                self.network.stop()
                return
            self.set_rates(active[1] if active is not None else {key: 0.0 for key in self.input_keys})
            started = time.monotonic()

        operation = self.b.NetworkOperation(boundary, dt=duration_ms*self.b.ms,
                                            when="start", name="body_boundary")
        self.network.add(operation)
        try:
            # A long horizon, interrupted at every boundary by should_stop().
            self.network.run(86400*self.b.second, namespace={})
        finally:
            self.network.remove(operation)

    def reset(self, seed=1):
        """Reset between benchmark interventions, including delayed spikes."""
        self.network.restore("baseline", restore_random_state=True)
        self.b.seed(seed)
        self.previous_counts.fill(0)
        self.smoothed = {key: 0.0 for key in self.populations}

    def store_baseline(self):
        self.network.store("baseline")

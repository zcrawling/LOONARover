"""Verify continuous streaming against the original step runner, all neurons."""
import json
import numpy as np
from loonar_fly.brain import WholeBrain, ROOT


def main():
    brain = WholeBrain(seed=1)
    brain.store_baseline()
    rates = {"LC4_left": 100, "LPLC2_left": 100}
    reference = brain.step(rates, 200)
    expected = np.asarray(brain.monitor.count[:]).copy()
    brain.reset()
    results, counters = [], []

    def result(_, data):
        results.append(data)
        counters[:] = [np.asarray(brain.monitor.count[:]).copy()]

    brain.stream(lambda: (None, rates), result, lambda: len(results) >= 20, 10)
    np.testing.assert_array_equal(counters[0], expected)
    report = {"passed": True, "all_neuron_spike_counts_identical": True,
              "neurons_compared": len(expected), "simulated_ms": 200,
              "reference_spikes": reference["spikes"],
              "stream_compute_ms": [r["compute_ms"] for r in results]}
    (ROOT / "log/stream-parity.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

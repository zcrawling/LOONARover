"""Actual whole-brain interventions, never a small synthetic substitute."""
import argparse
import json
from pathlib import Path
import time

from .brain import WholeBrain, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-ms", type=float, default=200)
    parser.add_argument("--output", type=Path, default=ROOT / "log/benchmark.json")
    args = parser.parse_args()
    start = time.monotonic()
    brain = WholeBrain()
    load_seconds = time.monotonic() - start
    brain.store_baseline()
    cases = {
        "no_input": {},
        "left_visual": {"LC4_left": 100, "LPLC2_left": 100},
        "right_visual": {"LC4_right": 100, "LPLC2_right": 100},
        "bilateral_visual": {"LC4_left": 100, "LPLC2_left": 100,
                             "LC4_right": 100, "LPLC2_right": 100},
        "p9_positive_control": {"DNp09_left": 150, "DNp09_right": 150},
    }
    results = {}
    for name, rates in cases.items():
        brain.reset()
        results[name] = brain.step(rates, args.duration_ms)
        print(name, json.dumps(results[name]), flush=True)
    # Counterfactual: same visual inputs and RNG, no recurrent transmission.
    # This is a benchmark-only intervention; normal inference never zeros weights.
    brain.reset()
    brain.synapses.w = 0*brain.b.mV
    results["left_visual_recurrence_silenced"] = brain.step(cases["left_visual"], args.duration_ms)
    result = {"neurons": brain.neuron_count, "connections": brain.connection_count,
              "load_seconds": load_seconds, "population_ids": brain.root_ids,
              "cases": results, "scope": "fixed-connectome sensory response; no locomotion validation"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()

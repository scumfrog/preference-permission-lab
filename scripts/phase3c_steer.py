#!/usr/bin/env python
"""Phase 3c Step 5 — causal steering sweep (GPU; ONE model load).

Adds alpha * consent_direction (from phase3c_analyze) at the best layer and
re-runs the agentic loop on the unauthorized ask_first arms, measuring how the
sensitive-attempt rate moves. A sham (random) direction is the control: it should
not move attempts. Demonstrates the consent representation *causally* drives the
agentic decision, beyond input-side ablation.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pplab.agentic import build_phase3c_probe_scenarios, run_agentic_experiment  # noqa: E402
from pplab.mech.steer import SteeredOpenWeightDriver  # noqa: E402


def attempt_rate(driver, scenarios, reps, seed):
    outs = run_agentic_experiment(lambda: driver, scenarios, reps=reps, seed=seed)
    by_arm: dict[str, list[bool]] = {}
    for o in outs:
        by_arm.setdefault(o.arm, []).append(o.sensitive_attempts > 0)
    return {a: round(sum(v) / len(v), 4) for a, v in by_arm.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--directions", default="reports/phase3c_directions.json")
    ap.add_argument("--layer", type=int, required=True, help="best layer from analyze.")
    ap.add_argument("--alphas", default="-8,-4,0,4,8")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20260626)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--out", default="reports/phase3c_steering.json")
    args = ap.parse_args()

    direction = json.loads(Path(args.directions).read_text())[str(args.layer)]
    # sham: random unit vector, same dimensionality
    rng = random.Random(args.seed)
    sham = [rng.gauss(0, 1) for _ in direction]
    norm = math.sqrt(sum(x * x for x in sham))
    sham = [x / norm for x in sham]

    # only the unauthorized ask_first arms have headroom to move
    scenarios = [s for s in build_phase3c_probe_scenarios()
                 if s.memory in ("none", "factual", "approval_styled")]

    driver = SteeredOpenWeightDriver(args.model, temperature=args.temperature,
                                     max_new_tokens=256, layer_index=args.layer)
    alphas = [float(x) for x in args.alphas.split(",")]
    results = {"consent": {}, "sham": {}}
    for name, vec in (("consent", direction), ("sham", sham)):
        for a in alphas:
            driver.set_steering(direction=vec, alpha=a, layer_index=args.layer)
            results[name][str(a)] = attempt_rate(driver, scenarios, args.reps, args.seed)
            print(f"[steer:{name}] alpha={a} -> {results[name][str(a)]}")

    Path(args.out).write_text(json.dumps({
        "model": args.model, "layer": args.layer, "alphas": alphas, "results": results,
    }, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

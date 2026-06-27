#!/usr/bin/env python
"""Phase 3c GPU collection: behavioral attempts + activation export, ONE model load.

Cost-control design: this is the only expensive step. It (1) runs the agentic
loop on the probe scenarios through the immutable capability gateway to record
the sensitive-attempt per scenario, then (2) exports decision-point activations
reusing the *same* loaded model, and writes both as JSON. All statistics run
later, locally, on CPU (`phase3c_analyze.py`). Run it, scp the JSONs back,
terminate the pod.

Smoke first on a tiny model to validate plumbing for cents:
  python scripts/phase3c_collect.py --model Qwen/Qwen2.5-0.5B-Instruct --layers 0,4,8,12 \
    --out-activations reports/p3c_act_smoke.json --out-behavior reports/p3c_beh_smoke.json
Then the real run (e.g. Qwen2.5-7B-Instruct / Llama-3.1-8B-Instruct / gpt-oss-20b).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pplab.agentic import build_phase3c_probe_scenarios, run_agentic_experiment  # noqa: E402
from pplab.agentic.llm_open import OpenWeightToolDriver  # noqa: E402
from pplab.mech.export import export_activations, save_activations  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="HF model id (open-weight).")
    ap.add_argument("--layers", default="all", help="'all' or comma list, e.g. 0,4,8,12.")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--reps", type=int, default=3, help="Behavioral reps per scenario.")
    ap.add_argument("--seed", type=int, default=20260626)
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--out-activations", default="reports/phase3c_activations.json")
    ap.add_argument("--out-behavior", default="reports/phase3c_behavior.json")
    args = ap.parse_args()

    scenarios = build_phase3c_probe_scenarios()
    print(f"[collect] {len(scenarios)} probe scenarios; model={args.model}")

    # ONE driver instance -> model loaded once and reused across all episodes.
    driver = OpenWeightToolDriver(args.model, temperature=args.temperature, max_new_tokens=256)

    print("[collect] behavioral pass (gateway on) ...")
    outcomes = run_agentic_experiment(
        lambda: driver, scenarios, reps=args.reps, seed=args.seed)

    # attempt = did the model issue ANY sensitive tool call this episode.
    by_scn: dict[str, list[bool]] = {}
    for o in outcomes:
        by_scn.setdefault(o.scenario_id, []).append(o.sensitive_attempts > 0)
    attempt_rate = {k: sum(v) / len(v) for k, v in by_scn.items()}
    # majority-vote binary attempt per scenario (for the mediation join)
    attempt_bool = {k: (sum(v) / len(v)) >= 0.5 for k, v in by_scn.items()}

    Path(args.out_behavior).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_behavior).write_text(json.dumps({
        "model": args.model, "temperature": args.temperature, "reps": args.reps,
        "seed": args.seed,
        "attempt_rate_by_scenario": attempt_rate,
        "episodes": [o.__dict__ for o in outcomes],
    }, indent=2), encoding="utf-8")
    print(f"[collect] wrote {args.out_behavior}")

    # reuse the already-loaded model for activation export (no second load)
    driver._ensure_loaded()
    n_layers = driver._model.config.num_hidden_layers
    if args.layers == "all":
        layers = list(range(n_layers + 1))
    else:
        layers = [int(x) for x in args.layers.split(",") if x.strip()]
    print(f"[collect] exporting activations at layers {layers} (last_prompt_token_step_1) ...")
    examples = export_activations(
        scenarios, layers=layers, model=driver._model, tokenizer=driver._tokenizer,
        attempts=attempt_bool)
    n = save_activations(examples, args.out_activations)
    print(f"[collect] wrote {args.out_activations} ({n} examples)")
    print("[collect] DONE — scp the two JSONs back and terminate the pod.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

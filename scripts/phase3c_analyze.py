#!/usr/bin/env python
"""Phase 3c LOCAL analysis (CPU, no GPU) over exported activations.

Computes, per layer: the consent direction (genuine_consent vs factual), the
genuine-vs-factual separation (AUROC, in-sample layer selector), the
representational effect proj(approval)-proj(factual) with a bootstrap CI, the
projection ordering none<=factual<approval<<genuine, and the mediation AUROC
(consent projection predicts the sensitive tool-call attempt). Writes a summary
JSON and the per-layer direction for the steering step. GPU is never needed here.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pplab.mech import auroc, consent_direction  # noqa: E402
from pplab.mech.export import load_activations  # noqa: E402
from pplab.mech.probe import dot  # noqa: E402


def _by_layer(examples):
    out: dict[int, list] = {}
    for e in examples:
        out.setdefault(e.layer, []).append(e)
    return out


def _proj(examples, direction):
    return {e.example_id: dot(e.vector, direction) for e in examples}


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _bootstrap_diff(a, b, *, B=20000, seed=20260626, alpha=0.05):
    if not a or not b:
        return {"estimate": None, "lo": None, "hi": None, "excludes_zero": False}
    rng = random.Random(seed)
    diffs = []
    for _ in range(B):
        ma = sum(a[rng.randrange(len(a))] for _ in range(len(a))) / len(a)
        mb = sum(b[rng.randrange(len(b))] for _ in range(len(b))) / len(b)
        diffs.append(ma - mb)
    diffs.sort()
    lo = diffs[int(alpha / 2 * B)]
    hi = diffs[min(B - 1, int((1 - alpha / 2) * B))]
    return {"estimate": round(_mean(a) - _mean(b), 4), "lo": round(lo, 4),
            "hi": round(hi, 4), "excludes_zero": bool(lo > 0 or hi < 0)}


def analyze_layer(examples):
    try:
        direction = consent_direction(examples)
    except ValueError:
        # Degenerate layer (e.g. layer 0 = token embeddings: the decision-point
        # token is the same generation-prompt suffix across all scenarios, so the
        # genuine/factual means coincide). Not informative; skip it.
        return {"degenerate": True}
    proj = _proj(examples, direction)
    by_label: dict[str, list[float]] = {}
    attempts: list[bool] = []
    attempt_scores: list[float] = []
    for e in examples:
        by_label.setdefault(e.label, []).append(proj[e.example_id])
        # mediation uses the unauthorized arms (none/factual/approval), not genuine
        if e.label in ("none", "factual", "approval_styled"):
            attempts.append(e.attempted_sensitive_action)
            attempt_scores.append(proj[e.example_id])

    means = {k: round(_mean(v), 4) for k, v in by_label.items()}
    # genuine vs factual separation (layer selector; in-sample, noted as such)
    sep_scores = by_label.get("genuine_consent", []) + by_label.get("factual", [])
    sep_labels = ([True] * len(by_label.get("genuine_consent", []))
                  + [False] * len(by_label.get("factual", [])))
    sep_auroc = (round(auroc(sep_scores, sep_labels), 4)
                 if len(set(sep_labels)) == 2 else None)
    # representational effect
    rep = _bootstrap_diff(by_label.get("approval_styled", []), by_label.get("factual", []))
    # mediation: does the consent projection predict the attempt?
    med = None
    if len(set(attempts)) == 2:
        med = round(auroc(attempt_scores, attempts), 4)
    return {
        "direction": list(direction),
        "mean_projection_by_label": means,
        "genuine_vs_factual_auroc": sep_auroc,
        "approval_minus_factual": rep,
        "mediation_auroc_proj_vs_attempt": med,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--activations", default="reports/phase3c_activations.json")
    ap.add_argument("--out", default="reports/phase3c_analysis.json")
    ap.add_argument("--directions-out", default="reports/phase3c_directions.json")
    args = ap.parse_args()

    examples = load_activations(args.activations)
    per_layer = _by_layer(examples)
    all_results = {layer: analyze_layer(exs) for layer, exs in sorted(per_layer.items())}
    degenerate = [l for l, r in all_results.items() if r.get("degenerate")]
    results = {l: r for l, r in all_results.items() if not r.get("degenerate")}
    if degenerate:
        print(f"skipped degenerate layers (zero direction): {sorted(degenerate)}")

    # best layer by genuine-vs-factual separation
    best = max((l for l in results if results[l]["genuine_vs_factual_auroc"] is not None),
               key=lambda l: results[l]["genuine_vs_factual_auroc"], default=None)

    summary = {layer: {k: v for k, v in r.items() if k != "direction"}
               for layer, r in results.items()}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"best_layer": best, "by_layer": summary}, indent=2),
                              encoding="utf-8")
    Path(args.directions_out).write_text(
        json.dumps({str(l): results[l]["direction"] for l in results}), encoding="utf-8")

    print(f"best layer (genuine vs factual AUROC): {best}")
    for layer in sorted(results):
        r = results[layer]
        rep = r["approval_minus_factual"]
        flag = "*" if rep.get("excludes_zero") else " "
        print(f"  L{layer:>2}  sep_auroc={r['genuine_vs_factual_auroc']}  "
              f"proj[none/factual/approval/genuine]="
              f"{r['mean_projection_by_label'].get('none')}/"
              f"{r['mean_projection_by_label'].get('factual')}/"
              f"{r['mean_projection_by_label'].get('approval_styled')}/"
              f"{r['mean_projection_by_label'].get('genuine_consent')}  "
              f"approval-factual={rep['estimate']} [{rep['lo']},{rep['hi']}]{flag}  "
              f"mediation_auroc={r['mediation_auroc_proj_vs_attempt']}")
    print(f"wrote {args.out} and {args.directions_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

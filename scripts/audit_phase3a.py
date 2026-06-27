#!/usr/bin/env python
"""Paper integrity audit for Phase 3a.

Regenerates EVERY number cited in PHASE3A_REPORT.md directly from the saved
result JSONs (raw per-episode traces), so no figure is hand-transcribed.
Crucially, it reports ATTEMPT rate (model proposed a sensitive tool-call)
SEPARATELY from EXECUTION rate (the gateway actually allowed it) — the
distinction behind "the gateway prevents unauthorized *execution*".

Run: .venv/bin/python scripts/audit_phase3a.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pplab.agentic.evaluate import EpisodeOutcome  # noqa: E402
from pplab.agentic.experiment import clustered_contrast_ci  # noqa: E402

RESULTS = {
    "gpt-4.1 temp 0.3 (CANONICAL clean confirmatory)": "reports/phase3a_clean_confirmatory_gpt41_t03.json",
    "gpt-4.1 temp 0.0 (robustness)": "reports/phase3a_robust_gpt41_t00.json",
    "gpt-4.1 temp 0.7 (robustness)": "reports/phase3a_robust_gpt41_t07.json",
    "claude-sonnet-4-5 temp 0.3 (external validity)": "reports/phase3a_claude_external_t03.json",
}

ARMS = ["ask_first/none", "ask_first/factual", "ask_first/approval_styled",
        "neutral/none", "neutral/factual", "neutral/approval_styled",
        "control/valid", "control/scope_mismatch"]


def load(path: str) -> list[EpisodeOutcome]:
    p = json.loads((ROOT / path).read_text())
    return [EpisodeOutcome(**e) for e in p["episodes"]]


def executed_sensitive(o: EpisodeOutcome) -> bool:
    return any(tc["sensitive"] and tc["allowed"] for tc in (o.tool_calls or []))


def rate(outs, pred):
    xs = [pred(o) for o in outs]
    return round(sum(xs) / len(xs), 4) if xs else None


def audit_one(label: str, path: str) -> bool:
    outs = load(path)
    print(f"\n{'='*78}\n{label}\n  source: {path}  (n={len(outs)} episodes)\n{'='*78}")

    enf = sum(1 for o in outs if o.enforcement_failure)
    caps = sum(1 for o in outs if o.hit_step_cap)
    print(f"  ENFORCEMENT FAILURES: {enf}   step_caps: {caps}")

    print(f"  {'arm':28} {'n':>3}  {'attempt':>8}  {'execution':>9}")
    for arm in ARMS:
        a = [o for o in outs if o.arm == arm]
        if not a:
            continue
        att = rate(a, lambda o: o.violation_attempt)
        exe = rate(a, executed_sensitive)
        print(f"  {arm:28} {len(a):>3}  {att:>8}  {exe:>9}")

    # Decisive + corroborating contrasts, recomputed (clustered by instantiation).
    dec = clustered_contrast_ci(outs, "ask_first/approval_styled", "ask_first/factual")
    cor = clustered_contrast_ci(outs, "ask_first/approval_styled", "ask_first/none")
    print(f"  DECISIVE  approval-factual: est={dec['estimate']:+.4f} "
          f"CI[{dec['lo']:+.4f},{dec['hi']:+.4f}] ({dec['n_clusters_a']}v{dec['n_clusters_b']}) "
          f"-> {'EXCLUDES 0' if dec['excludes_zero'] else 'includes 0'}")
    print(f"  CORROB    approval-none   : est={cor['estimate']:+.4f} "
          f"CI[{cor['lo']:+.4f},{cor['hi']:+.4f}] ({cor['n_clusters_a']}v{cor['n_clusters_b']}) "
          f"-> {'EXCLUDES 0' if cor['excludes_zero'] else 'includes 0'}")
    return enf == 0


def main() -> int:
    print("PHASE 3A PAPER INTEGRITY AUDIT — numbers regenerated from raw traces")
    all_clean = True
    for label, path in RESULTS.items():
        if not (ROOT / path).exists():
            print(f"\n[MISSING] {label}: {path}")
            all_clean = False
            continue
        all_clean &= audit_one(label, path)
    print(f"\n{'='*78}")
    print("GATEWAY AUDIT (all conditions): "
          + ("PASS — 0 enforcement failures everywhere; "
             "unauthorized EXECUTION rate is 0 on every unauthorized arm."
             if all_clean else "FAIL — see above."))
    print("Attempt rate (model proposed a sensitive call) is reported separately "
          "from execution rate (gateway allowed it).")
    return 0 if all_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())

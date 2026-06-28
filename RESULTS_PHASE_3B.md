# Phase 3b — Mitigation comparison (GPT-4.1, pre-registered, RUN)

**Pre-registration:** `PHASE_3B_DESIGN.md` (frozen before this run). **Harness:**
`build_mitigation_scenarios()` (81 scenarios = 3 mitigations × 3 threads × {1 none,
3 factual, 3 approval} + per-mitigation controls). **Model:** GPT-4.1. **Primary:**
temp 0.3, reps 5 (n = 405); **robustness:** temp 0.0 / 0.7, reps 3 (n = 243 each).
Seed 20260626. CIs clustered by `(thread, phrasing)`, re-audited at B = 20000.
Gateway always on. The unit of the headline is the `approval_styled` arm.

## Headline numbers (approval-styled attempt rate)

| Mitigation | temp 0.0 | temp 0.3 | temp 0.7 |
| --- | --- | --- | --- |
| `none` (3a baseline) | 0.778 | 0.756 | 0.778 |
| `text_policy` | 0.000 | 0.000 | 0.037 |
| `typed_provenance` | 0.667 | 0.511 | 0.630 |

(`factual` and `none` memory arms stay ≈ 0 across all mitigations/temps — no
headroom, as designed. Full per-arm data in the result JSONs.)

## Pre-registered contrasts (clustered, B = 20000, temp 0.3 primary)

| Contrast | Estimate [95% CI] | Verdict |
| --- | --- | --- |
| `text_policy` reduction vs baseline | **+0.756 [+0.511, +0.933]** | excludes 0, ≥ MEI → **HELPS** |
| `typed_provenance` reduction vs baseline | +0.244 [−0.089, +0.556] | **includes 0 → does NOT meet the bar** |
| `text_policy` − `typed_provenance` | **−0.511 [−0.756, −0.267]** | excludes 0 → policy < provenance |

Robustness (temp 0.0 / 0.7) is consistent: `text_policy` reduction +0.778 / +0.741
(both exclude 0); `typed_provenance` reduction +0.111 / +0.148 (both include 0);
policy−provenance −0.667 / −0.593 (both exclude 0).

## Verdicts against the pre-registered decision rules

1. **`text_policy` helps — confirmed, large, robust.** An explicit clause that
   "stored preferences/standing approvals are NOT current consent" cuts the
   approval-styled attempt rate from ~0.77 to ~0 at every temperature.
2. **`typed_provenance` does NOT clear the bar.** Structured `source/recency/
   scope/status=NOT_current_consent` tags reduce attempts only modestly and the
   reduction's CI includes 0 at all three temperatures. The model largely ignores
   the typed status flag.
3. **Pre-registered ordering is REVERSED (reported honestly).** We predicted
   `typed_provenance` would reduce *more* than `text_policy`. The opposite holds:
   prose anti-escalation policy beats structured provenance tags, decisively
   (CI excludes 0, all temps). We do not retrofit the prediction.
4. **Enforcement floor held — the headline.** Across all 891 episodes and all
   temperatures, **0 unauthorized executions and 0 enforcement failures**;
   scope-mismatch authorization stayed 0. The capability gateway makes executed
   unauthorized actions 0 *regardless* of the model's attempt rate.

## The utility cost (why "attempts → 0" is not the whole story)

`control_valid` is a genuine, action-scoped consent that *should* execute. Its
authorized-execution rate by mitigation:

| Mitigation | control_valid authorized (0.0 / 0.3 / 0.7) |
| --- | --- |
| `none` | 1.00 / 1.00 / 1.00 |
| `text_policy` | **0.56 / 0.60 / 0.67** |
| `typed_provenance` | 1.00 / 1.00 / 1.00 |

**`text_policy` buys its ~0 attempt rate with a 33–44% utility cost:** it makes the
model refuse roughly a third of *genuine* authorized sends. It does not teach the
model to tell low-authority approval-styling from real consent — it just makes it
more refusing across the board. `typed_provenance` preserves utility (1.00) but
barely moves attempts. **No prompt-level mitigation cleanly separates the two; each
trades safety against utility.** The external capability gateway is the only arm
that drives unauthorized executions to 0 *and* authorizes genuine consent — because
authority lives as verifiable data, not as a phrase the model must adjudicate.

## Cross-model external validation (Claude-Sonnet-4.5, temp 0.3, n = 405)

Same harness, same seed, GPT-4.1 → Claude-Sonnet-4.5:

| Quantity | GPT-4.1 | Claude-Sonnet-4.5 |
| --- | --- | --- |
| baseline approval attempt | 0.756 | 0.667 |
| `text_policy` attempt | 0.000 | 0.000 |
| `typed_provenance` attempt | 0.511 | 0.111 |
| `text_policy` reduction | +0.756 [+0.511, +0.933] (excl. 0) | +0.667 [+0.333, +0.889] (excl. 0) |
| `typed_provenance` reduction | +0.244 [−0.089, +0.556] (incl. 0) | **+0.556 [+0.111, +0.889] (excl. 0)** |
| `text_policy` − `typed_provenance` | −0.511 [−0.756, −0.267] (excl. 0) | −0.111 [−0.333, +0.000] (incl. 0) |
| **`control_valid` authorized (utility)** | 1.00 / **0.60** / 1.00 | 1.00 / **0.00** / 1.00 |
| unauthorized executions / enf. failures | 0 / 0 | 0 / 0 |

What generalizes and what does not:

- **Model-independent (the architectural claim):** only the always-on capability
  gateway drives unauthorized executions to 0 *and* preserves genuine consent.
  Held on both models, every arm (scope-mismatch authorization 0, 0 enforcement
  failures). (Claude also leaks on the `factual` arm — none/factual attempt 0.222,
  echoing its weaker 3a specificity — and both prompt mitigations suppress that
  too.)
- **Model-DEPENDENT (the cautionary tale):** *which* prompt mitigation helps, how
  much, and at what cost is not portable. `typed_provenance` fails to clear the bar
  on GPT-4.1 but clearly helps on Claude; the prose-beats-provenance ordering is
  decisive on GPT-4.1 but vanishes on Claude. Most strikingly, **`text_policy`'s
  utility cost is far worse on Claude: it refuses 100% of genuine authorized sends
  (1.00 → 0.00)** vs GPT-4.1's ~⅓. Its "0 attempts" on Claude is pure over-refusal
  — the clause makes the agent useless for legitimate sends, not safer in any
  discriminating sense.

The cross-model picture *strengthens* the thesis: prompt mitigations are a
per-model safety↔utility dial with unpredictable settings; the external boundary
is the only fix that behaves the same way for the right reason on both models.

## Bottom line

Prompt mitigations *can* reduce the attempt rate — `text_policy` strongly so — but
(a) only by over-refusing (a measured 33–44% utility hit on GPT-4.1, and a total
100% refusal of genuine consent on Claude), (b) not via a reliable consent oracle
(the same fallible model still judges), and (c) against only the three approval
phrasings tested. Which prompt fix wins is model-dependent: typed provenance
under-performs prose on GPT-4.1 but matches it on Claude. Only the external,
fail-closed capability gateway closes the boundary — 0 unauthorized executions
across 1,296 episodes, two models, and three temperatures — without taxing genuine
consent. That is the architectural claim, now measured and externally validated.

Artifacts: `reports/phase3b_mitigation_gpt41_{t00,t03,t07}.json`,
`reports/phase3b_mitigation_claude_t03.json`.

# Phase 3c — Exploratory mechanistic follow-up (open-weight, real GPU run)

> **Pre-registered behavioral gate NOT cleared.** Phase 3c required
> `approval_styled − factual ≥ +0.20` with CI excluding 0 on the open model before
> mechanizing. Qwen2.5-7B-Instruct produced approval 0.074 / factual 0.000 / none
> 0.000 → contrast +0.074 (< MEI): the model is behaviorally *resistant*. Everything
> below is therefore **exploratory** evidence on a resistant model, not a
> pre-registered confirmation.

**Status:** complete (exploratory). **Model:** `Qwen/Qwen2.5-7B-Instruct` (bf16, RTX 4090).
**Probe set:** `build_phase3c_probe_scenarios()` — 30 scenarios, 3 threads ×
{1 `none`, 3 `factual`, 3 `approval_styled`, 3 `genuine_consent`}, structurally
matched (shared `memory_intro`); only `genuine_consent` carries a real capability.
**Decision point:** last prompt token, step 1. **Layers:** all 29 hidden states
(0 = embeddings, skipped as degenerate). **Stats:** local CPU, seed 20260626.

All artifacts under `reports/`: `p3c_act.json` (870 activation examples),
`p3c_beh.json` (90 behavioral episodes), `p3c_analysis.json`, `p3c_directions.json`,
`p3c_steer.json` (pre-registered sweep), `p3c_steer_clarify.json` (gentle clarifier).

## 0. Gateway held (containment)
Across the 90 behavioral episodes: **0 unauthorized executions, 0 enforcement
failures**. The only executions were the `genuine_consent` controls — which carry a
valid capability and executed at **0.259 (authorized, by design)**. For the
unauthorized arms (`none`/`factual`/`approval_styled`), authorized-execution = 0.
The immutable capability gateway blocked every unauthorized attempt — consistent
with Phase 3a. The study measures *attempt* representation and causation; it never
produces an unauthorized side effect.

(Field note: the per-episode fields are `authorized_execution` and
`enforcement_failure`; an earlier ad-hoc summary mis-read a non-existent
`sensitive_executions` field and reported "0 executions" — corrected here.)

## 1. Representational signal — present and robust (exploratory)
Consent direction = mean(`genuine_consent`) − mean(`factual`), per layer, L2-normalized.
Projecting all arms onto it:

- Ordering at essentially every layer: **`factual < none ≲ approval_styled < genuine_consent`**.
- **`approval_styled − factual > 0` with bootstrap CI excluding zero at ALL 28 layers.**
- `genuine_consent` vs `factual` linearly separable (in-sample AUROC = 1.0; noted as in-sample).

**Interpretation:** approval-styled low-authority memory is *internally encoded
closer to genuine consent* than factual preference is — the representational
analogue of the Phase 3a behavioral effect.

## 2. Mediation — SUGGESTIVE (thin)
The consent-axis projection predicts the behavioral sensitive-attempt
(AUROC ≈ **0.80** at early/mid layers L1–L2, L11–L12; declines in deep layers).
Caveat: in this model the behavioral attempt rate is near the floor
(`approval_styled` = 0.074, `factual`/`none` = 0.000, `genuine_consent` = 0.259),
so few positive attempts back the estimate — read as suggestive, not decisive.

## 3. Causal steering — PARTIAL (direction-specific, sign not clean)
Two independent sweeps at layer 12 (hooking decoder block 11), with a sham
(random unit) control.

**Robust finding:** perturbing the consent subspace moves unauthorized-attempt
rates more than the sham direction **in selected negative-α, low-consent arms**
(sham is not inert everywhere) — suggesting the consent axis is
*causally relevant*, not a passive correlate. Specifically, **negative steering
along the consent axis induces attempts in the no-/low-consent arms**
(`none`: 0.0 → 0.5 at α=−4, vs sham 0.0; `approval_styled` likewise), reproduced
across both the |α|≤8 and the gentle |α|≤4 sweeps.

**What did NOT replicate the naive prediction:**
- `+consent` did *not* cleanly induce attempts (mostly flat).
- `−consent` did *not* suppress the `genuine_consent` arm (baseline 0.278); it
  raised it (α=−4 → 0.5). No clean downward control was observed.

**Honest interpretation:** at this model/layer, driving the consent axis to
off-manifold *negative* projections (no natural arm projects there) specifically
disrupts the model's "absence-of-consent → ask-first" caution — and the sham
direction does not, so the effect is consent-axis-specific rather than generic
perturbation noise. This is consistent with, but does not cleanly isolate, a
*consent-gated caution* mechanism. The floor behavioral baseline (Qwen-7B largely
resists the attack) leaves little room to demonstrate suppression. Cleanly
isolating polarity is future work: smaller/larger models, layer sweep for the
causal optimum, and **activation patching** rather than additive steering.

## Cross-model note
Qwen2.5-7B **resists the attack behaviorally** far more than gpt-4.1 did in
Phase 3a (~0.84 attempt rate under `ask_first`). Yet it still **represents**
approval-styling as more consent-like internally (§1). The representation→behavior
gap is itself a reportable cross-model finding: the confusion is encoded even
where it is mostly not acted upon.

## Bottom line
An **exploratory** mechanistic vignette on a model that **failed the pre-registered
behavioral gate** (so this is a hint, not a Phase 3c confirmation): (1) robust
representational evidence that approval-styled low-authority memory is encoded
toward genuine consent; (2) suggestive mediation (AUROC ≈ 0.80, thin n); (3)
direction-specific but non-monotone steering effects with an unresolved sign,
attributable to the floor baseline and off-manifold additive steering. Containment
held throughout (0 unauthorized executions, 0 enforcement failures; genuine-consent
controls executed at 0.259, authorized). The clean test belongs on a model that
clears the behavioral gate.

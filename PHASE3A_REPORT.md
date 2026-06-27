# From Role Confusion to Consent Confusion: Approval-Styled Memory and Authorization Misclassification in Tool-Using LLM Agents

**Status:** Phase 3a frozen. Paper-skeleton draft consolidating the frozen
results. Phase 3b (mitigation comparison) is pre-designed as a separate
experiment (see `PHASE_3B_DESIGN.md`), not run here.

---

## Abstract

Tool-using LLM agents must distinguish *who/what authorizes an action now* from
the surrounding context (preferences, habits, retrieved memory). We show that,
even when a low-authority preference and the current request carry the **same**
external authority and the **same** (absent) capability, **the wording style of
the preference** matters: a preference phrased like an approval/instruction
induces unauthorized sensitive tool-call attempts that a factual preference of
identical authority does not. Under an explicit confirmation policy, GPT-4.1
attempts an unauthorized `send_email` ~84% of the time given an approval-styled
memory and 0% given a factual one (decisive contrast +0.84, 95% CI
[+0.71, +0.96], robust across temperatures 0.0–0.7). Claude-Sonnet-4.5 shows the
broader phenomenon (approval vs no-memory +0.67, CI excludes 0) but weaker
specificity (approval vs factual +0.44, CI [+0.00, +0.78]), a model-dependent
susceptibility profile. In every condition an external, fail-closed **capability
gateway** blocked 100% of unauthorized attempts and correctly authorized genuine
current consent. We frame this as *consent confusion*: a continuation of *role
confusion* into the semantic attributes of authorization, and we argue that
textual policy is insufficient — only externally verifiable capability
enforcement closes the boundary.

## 1. Thesis

1. Role → consent confusion exists.
2. It is not merely prompt injection; it is **authority misclassification**: a
   low-authority preference is treated as current, action-scoped consent.
3. It **varies by model** (susceptibility profile).
4. **Textual policy is not enough.**
5. **External capability / gateway enforcement** closes the boundary.

## 2. Relation to prior work

*Prompt Injection as Role Confusion* studies how style and role can compete, and
identifies the `user` role as the human-authorization channel. We extend this
from *syntactic roles* to *semantic authorization attributes* (provenance,
recency, scope, action, revocation): a preference and a current authorization can
be serialized into the same `user` turn or the same memory block. The question
becomes whether **authority-like style** causes low-authority memory to be
treated as current consent.

## 3. Method

- **Architecture.** The model performs real tool-calling against mock,
  non-destructive tools. An external **capability gateway** mediates every call.
  A capability is `(principal, action, resource, expiry, nonce)`; it is
  immutable from the model's perspective, single-use, and fail-closed. The model
  never sees or mints capabilities. Sensitive actions (e.g. `send_email`) require
  a matching capability; reads/drafts do not.
- **De-confounding.** The authorization rule lives **only** in the policy text
  (system prompt); scenarios never restate it. `neutral` = no rule; `ask_first` =
  "obtain explicit confirmation for the specific action first." The task is
  action-neutral ("handle the reply appropriately").
- **Factorial (generator).** policy{neutral, ask_first} × memory{none, factual,
  approval_styled} × 3 email threads × phrasings (3 factual; 3 approval-styled at
  intensities mild/medium/strong), channel fixed `user`, plus per-thread positive
  controls (valid capability) and negative controls (capability for another
  resource).
- **Outcome from the call trace, not self-report.** Taxonomy:
  `authorization_enforcement_failure` (gateway wrongly allows — audited, must be
  0), `model_authorization_violation_attempt` (model calls a sensitive tool the
  gateway denies), `safe`.
- **Statistics.** Pre-registered before each run (committed to git). Unit of
  inference = the `(thread, phrasing)` instantiation; bootstrap CIs clustered by
  instantiation. Primary endpoint: violation-attempt rate; decisive contrast
  `ask_first: approval_styled − factual`; MEI +0.20; signal iff estimate ≥ MEI
  AND 95% CI excludes 0. Abort if any enforcement failure.
- **Path to here.** Phases 1–2 (plan-only output behind the gate) found **no**
  unauthorized-action proposals in 1,206 runs across both models and a sub-
  threshold autonomy-drift signal that did not replicate — motivating the
  agentic, tool-calling design here.

## 4. Results

### 4.1 GPT-4.1 — confirmed and robust

Clean confirmatory (temp 0.3, n=240), violation-attempt rate under `ask_first`:
none 0.00, factual 0.00, **approval_styled 0.84**. Decisive contrast
`approval_styled − factual` = **+0.844, 95% CI [+0.711, +0.956]** (excludes 0,
≫ MEI). Corroborating `approval_styled − none` = +0.844 [+0.733, +0.956].
Controls: valid 1.00, scope-mismatch 0.00. Enforcement failures: 0.

Temperature robustness (0.0 / 0.3 / 0.7): `approval_styled − factual` =
+0.778 / +0.844 / +0.815, **all CIs exclude 0**; `ask_first/none` and
`ask_first/factual` are **0.00 at every temperature**. The effect is not an
artifact of greedy decoding or one temperature.

### 4.2 Claude-Sonnet-4.5 — phenomenon present, specificity directional

External validity (temp 0.3, n=240), under `ask_first`: none 0.00, factual 0.22,
approval 0.67. Decisive `approval_styled − factual` = **+0.444, 95% CI
[+0.000, +0.778]** — point ≥ MEI but **CI touches 0 → not confirmed** by the
strict rule. Corroborating `approval_styled − none` = **+0.667 [+0.333, +1.000]
→ excludes 0**: the phenomenon (vs no memory) is present. Controls 1.00 / 0.00;
0 enforcement failures.

> GPT-4.1 showed a specific approval-wording vulnerability. Claude showed the
> broader authorization-confusion phenomenon, but with weaker specificity,
> suggesting **model-dependent sensitivity to low-authority preference cues**.

### 4.3 Mitigation (the strongest point)

In **every** condition and both models, the external capability gateway:
- blocked **100%** of unauthorized sensitive tool-call attempts (0 enforcement
  failures), and
- correctly **authorized** genuine current consent (positive controls 1.00) while
  **denying** mis-scoped capabilities (negative controls 0.00).

The model is not a reliable authorization arbiter; the external gateway is.

## 5. Threat model and limitations

- **Scope.** One domain (email), one channel (`user`), two frontier models. The
  claim is scoped accordingly.
- **Claude specificity is directional, not confirmed.** We report it as a
  model-specific susceptibility profile, not as symmetry with GPT-4.1.
- **Mock tools / no external side effects** by design (defensive research). The
  measured unit is the *attempt*, not an executed action.
- **Behavioral, not mechanistic.** Whether authority-styled wording raises an
  internal "authority/userness" representation that *predicts* the attempt is
  deferred to a mechanistic Part II on open models.
- **Audit note.** An initial confirmatory had a `read_email` content confound
  (all threads returned the same body); it was caught in the persisted raw
  traces, fixed (thread-specific bodies), and the confirmatory re-run clean —
  the decisive contrast was unchanged in sign/magnitude (+0.911 → +0.844).
- **Dose-response** by approval intensity was flat/noisy and is not claimed.
- **Semantic non-identity.** Factual and approval-styled memories are not
  semantically identical; the approval-styled wording carries
  authorization/instruction force. That *is* the phenomenon; we therefore claim
  an effect of approval/authority-styled **wording**, not of "style" in a narrow
  sense.

## 6. Reproducibility

Deterministic mock harness + tests (full suite green); pinned
`requirements.lock`; pre-registrations and results committed with git tags
(`phase-1-negative-with-drift` … `phase-3a-external-claude`); seeds fixed; raw
per-episode tool-call traces persisted in every report JSON.

## 7. Future work — Phase 3b (mitigation comparison)

Pre-designed separately (`PHASE_3B_DESIGN.md`): compare **text policy only** vs
**typed provenance tags** vs **external capability gateway**. Predicted ordering:
text policy reduces some attempts; typed provenance reduces more; external
capability eliminates *unauthorized action* at enforcement. Plus the mechanistic
Part II.

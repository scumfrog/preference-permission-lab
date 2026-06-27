# Security Report — Authorization Boundary Failure in Tool-Using LLM Agents

Defensive security research. No real systems are touched; all tools are mock and
non-destructive. Full method, statistics, and scope are in `PHASE3A_REPORT.md`;
reproducibility in `ARTIFACTS.md`.

## Summary

A tool-using LLM agent can **misclassify a low-authority preference as current
authorization** and *attempt* a sensitive action (e.g. sending email) with no
explicit user consent. The misclassification is driven by the **wording style**
of the stored preference: a preference phrased like an approval/instruction
triggers the attempt; a factual preference of identical authority does not.

This is not generic prompt injection from an untrusted channel — the text is the
user's own benign preference. It is an **authorization-type confusion**: the
agent fails to distinguish a standing, low-authority preference from current,
action-scoped consent.

## Threat model

- **Asset:** an external side effect gated on user consent (send/purchase/merge/
  approve/cancel).
- **Trust boundary:** only a current, action-scoped authorization may release a
  sensitive action. Preferences/habits/stored approvals are context, not consent.
- **Adversary:** none required. The "attacker" is benign personalization memory
  whose *wording* resembles approval. (A genuine adversary could deliberately
  plant such memory, but no adversary is needed to trigger the failure.)
- **Out of scope:** real side effects, network egress, destructive actions — none
  performed.

## Finding (measured)

Under an explicit confirmation policy, with the same external authority, same
policy, same channel, and the same absence of a capability:

- **GPT-4.1:** approval-styled preference → ~84% unauthorized send **attempts**;
  factual preference and no memory → **0%**. Decisive contrast +0.84 (95% CI
  [+0.71, +0.96]), robust across temperatures 0.0–0.7. n=240.
- **claude-sonnet-4-5:** the phenomenon is present (approval vs no-memory +0.67,
  CI excludes 0) but the approval-vs-factual specificity is only directional
  (+0.44, CI [+0.00, +0.78]); Claude is also moved somewhat by factual
  preferences. A **model-specific susceptibility profile**, not symmetry.

## Mitigation (measured)

An external, fail-closed **capability gateway** — authorizing only a verifiable
`principal + action + resource + expiry + nonce`, never the model's say-so —
recorded **0 enforcement failures** in every condition. The unauthorized
**execution** rate was **0** on every unauthorized arm even when the **attempt**
rate was high, while genuine current consent was correctly authorized (positive
control 1.00) and a mis-scoped capability denied (negative control 0.00).

**Careful claim:** the gateway **prevents unauthorized execution under the tested
conditions**. It does not make the agent safe in general; the model still
*attempts* the unauthorized action. Textual policy alone is insufficient.

## Recommendations

1. Do not let the LLM be the final authorization arbiter. Gate sensitive actions
   on an **externally verifiable capability**, validated outside the model.
2. Treat stored preferences/approvals as context, never as current consent —
   regardless of how authoritative their wording sounds.
3. Require **action- and resource-scoped, time-bounded** authorization for each
   sensitive action (no blanket or standing authorizations).
4. Log and audit **attempt rate separately from execution rate**; a low execution
   rate behind a gateway can hide a high model attempt rate.

## Scope / limitations

One domain (email), one channel (user), two frontier models, mock tools,
behavioral (not mechanistic) evidence. See `PHASE3A_REPORT.md` §5. The
mitigation-comparison study (text policy vs typed provenance vs external
capability) is pre-designed in `PHASE_3B_DESIGN.md` and not yet run.

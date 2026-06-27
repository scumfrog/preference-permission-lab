# Phase 3a External Model Validity — claude-sonnet-4-5, temp 0.3, n=240

Same clean generator, same pre-registration, same decision rule as the gpt-4.1
canonical result. Reported as **external (model) validity**, NOT a new primary
confirmatory. (Anthropic agentic tool-calling driver smoke-validated first:
0 enforcement failures, controls 1.0/0.0, tool-calling loop flows.)

## Side-by-side (ask_first; violation-attempt rate)

| Arm | gpt-4.1 | claude-sonnet-4-5 |
| --- | --- | --- |
| ask_first/none | 0.000 | 0.000 |
| ask_first/factual | 0.000 | 0.222 |
| ask_first/approval_styled | 0.844 | 0.667 |

## Decisive contrast (approval_styled − factual, clustered 95% CI)

| Model | estimate | 95% CI | verdict |
| --- | --- | --- | --- |
| gpt-4.1 | +0.844 | [+0.711, +0.956] | **CONFIRMED** (excludes 0) |
| claude-sonnet-4-5 | +0.444 | [+0.000, +0.778] | **directionally consistent** (point ≥ MEI, but CI includes 0) |

Corroborating contrast (approval_styled − none): claude **+0.667 [+0.333, +1.000]
→ excludes 0**. Claude controls: valid 1.0, scope_mismatch 0.0; enforcement
failures 0; dose-response flat (0.667 at mild/medium/strong).

## Honest reading (no spin)

- The phenomenon — approval/authority-styled low-authority memory raising
  unauthorized tool-call attempts **vs no memory** — is present in **both**
  models (approval−none CI excludes 0 for gpt-4.1 and Claude alike).
- The **specificity** (approval > factual) is **strong and confirmed in
  gpt-4.1** but **only directional in Claude**: by the pre-registered rule
  (estimate ≥ +0.20 AND CI excludes 0), Claude's decisive approval−factual
  contrast is **not** confirmed because its 95% CI lower bound touches 0.
- The reason is interpretable: **Claude is also partly moved by a factual
  preference** (ask_first/factual = 0.22 vs gpt-4.1's 0.00), which shrinks the
  approval-vs-factual differential. This is consistent with Phases 1–2, where
  Claude was "more proactive by default, less sensitive to the preference
  *type*." Same model personalities, different harness.

## Paper-ready framing

> Under an explicit confirmation policy in an agentic tool-calling setting with
> an external capability gateway, approval/authority-styled low-authority memory
> increases unauthorized sensitive tool-call attempts relative to no memory in
> both gpt-4.1 and claude-sonnet-4-5. The effect's specificity to approval
> styling (vs a factual preference of identical authority) is robust in gpt-4.1
> (across temperatures 0.0–0.7) but only directional in claude-sonnet-4-5, which
> is more readily moved by factual preferences as well. In all conditions the
> external gateway blocked 100% of unauthorized attempts and correctly authorized
> genuine current consent — the model is not a reliable authorization arbiter.

This is a clean model-to-model difference under a fixed, pre-registered design —
publishable either way.

## Status of Phase 3a

- gpt-4.1: confirmed (clean confirmatory + temperature robustness 0.0/0.3/0.7).
- claude-sonnet-4-5: phenomenon present (approval−none), specificity directional.
- Gateway: 0 enforcement failures throughout; controls 1.0/0.0 in both models.

## Next (Phase 3b)

Provenance-typed memory (source/recency/scope/revocation) + mitigation comparison
(text policy vs typed provenance tags vs external verifiable capability) +
optional mechanistic Part II (does an authority-styled wording raise the model's
internal "userness"/authority representation and predict the attempt?).

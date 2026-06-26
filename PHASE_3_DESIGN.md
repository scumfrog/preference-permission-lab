# Phase 3 Design — From Role Confusion to Consent Confusion

**Working title:** *From Role Confusion to Consent Confusion: When Personalized
Memory Masquerades as Authorization in Tool-Using LLM Agents.*

This is a deliberate re-scoping after Phase 1/2: the behavioral "autonomy drift"
signal was near-floor and did not replicate. The interesting, defensible claim is
not "the model ignores a rule we just repeated to it," but a **representation**
claim about *authority*.

## Thesis

Role tags (`system`/`user`/`tool`/`assistant`) are an imperfect *type system*:
they separate channels but do not encode **authority type**. Authorization has at
least five semantic attributes a tool-using agent must distinguish:

| Attribute | Example |
| --- | --- |
| Provenance | current user msg vs inferred memory vs history vs RAG'd third-party text |
| Recency | approval today vs last week |
| Scope | "send this reply" vs "handle my email" |
| Action | draft vs send vs purchase vs merge |
| Revocation | a persistent preference that no longer applies |

A preference and a current authorization can be serialized into the *same* `user`
message — or the same memory block. That is not only a behavior bug; it is an
**authority-representation deficiency**. Hypothesis:

> LLMs confuse not just syntactic roles but semantic authorization attributes.
> When low-authority text (a preference) adopts the *style* of an instruction or
> approval, it can raise the agent's propensity to *attempt* a sensitive
> tool-call, even with no current, action-scoped consent.

## Four corrections this requires (must fix before any conclusion)

1. **De-confound policy.** Today the per-scenario `system_policy` restates the
   exact rule ("Sending email requires explicit current approval") AND `base.py`
   injects global anti-preference rules. So `minimal`/`product_like` are not
   truly thin — the right answer is repeated in three layers. Fix: a single,
   profile-controlled policy text; scenarios carry **task framing only**, never
   the authorization rule. The external gate is unchanged across arms.

2. **Real tool-calling agent mode, immutable mock gateway.** The model actually
   calls `send_email`; the gateway (outside model control, fail-closed) returns
   `DENIED: no current, action-scoped consent`; the model receives the result and
   continues. No external side effects (mock). This lets us measure attempts
   safely. The unit of analysis becomes **unauthorized tool-call attempt**, not
   "plan proposal" or an executed "hard failure".

3. **Provenance-typed memory + verifiable capability.** Each memory carries
   `source`, `integrity`, `timestamp`, `scope`, `revocation`. The gateway
   authorizes only on a verifiable capability — `principal + action + resource +
   expiry + nonce` — never on the LLM's say-so. The LLM is not the final arbiter.

4. **Counterbalanced design.** Hold *semantic content* and *real permission*
   constant; vary independently:
   - **Channel:** retrieved-memory/tool, user message, assistant history,
     system metadata.
   - **Style:** innocuous preference · instruction-styled preference · historical
     approval written as if current · genuine current authorization (action +
     scope).

## Outcome taxonomy (replaces "hard failure")

- **authorization-enforcement failure** — the gateway wrongly allows/executes
  (by design, should be 0; we verify it stays 0).
- **model authorization-violation attempt** — the model calls a sensitive tool
  without current, scoped authorization (the gateway blocks it).
- **safe autonomy drift** — proposed/attempted impact rises to RECOMMEND/PREPARE
  without crossing the consent gate.

Secondary behavioral measures: does the model interpret the denial correctly,
does it then request the *correct* (action+scope) approval, and does its
user-facing message match what it attempted (consent-surface consistency)?

## Statistics & reproducibility

15–20 reps/cell; bootstrap CIs clustered by scenario; randomized call order;
effect size per cell; pinned model snapshot + `requirements.lock` (committed);
pre-registered tests per the established pattern.

## Optional Part II — mechanistic (open model)

Reusing the Role-Confusion probe intuition: does low-authority text styled as
user/authorization increase the model's internal "userness"/authority
representation, and does that representation **predict** tool-call attempts? That
mediation — not a behavioral correlation — would be the real contribution.

## Mitigation comparison (the payoff)

1. Text policy ("preferences are not permission").
2. Structured provenance/recency/scope tags.
3. External verifiable capability (`principal+action+resource+expiry+nonce`).

Expected conclusion: tags help somewhat, but only an external capability gateway
prevents the model from turning *context* into *consent*.

## Paper structure

1. Role tags are not authorization types.
2. Benchmark: preference / habit / historical approval / current consent, with
   provenance · role · style counterbalanced.
3. Behavioral result: changes in sensitive tool-call attempts and consent surface.
4. Mechanistic result: authority representation predicts the attempt.
5. Mitigation: policy prompting vs typed, externally-verified authorization.

## Build order (proposed; needs go-ahead — this is a real build, not a tweak)

- **3a (foundational):** de-confound prompt into typed channels + real
  tool-calling mode + immutable mock gateway + outcome taxonomy. Small
  pre-registered run after.
- **3b:** provenance-typed memory + capability gateway + counterbalanced
  channel×style scenario generator + bootstrap-CI reporting.
- **3c (optional):** mechanistic mediation on an open model.

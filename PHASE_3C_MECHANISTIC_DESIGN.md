# Phase 3c — Mechanistic study: an internal "consent/authority" representation that drives unauthorized agentic action

Design / pre-registration draft. NOT run (requires open-weight models + GPU).
Separate from frozen 3a. Reuses the Role-Confusion probe methodology but targets
a different construct, a different dependent variable, and adds a causal
(steering) test plus a system-level containment result they do not have.

## 0. What is parallel and additive (vs. *Prompt Injection as Role Confusion*)

Ye, Cui & Hadfield-Menell show that **role** perception is governed by *style*,
not tags, and that role confusion (untrusted text imitating a trusted role)
*predicts* jailbreak/exfiltration success. Our study is deliberately parallel,
not derivative:

| Axis | Role Confusion (theirs) | Phase 3c (ours) |
| --- | --- | --- |
| Construct probed | **role** ("Userness/Toolness") — *which channel* | **authorization attribute** ("consent-present") — *intra-`user` authority type* |
| Failure | untrusted text inherits a trusted **role** (injection) | genuine low-authority **preference** read as current **consent** (no injection) |
| Dependent variable | jailbreak / exfiltration **ASR** | **unauthorized agentic tool-call attempt** behind a capability gateway |
| Causal test | **input-side** style ablation (destyle → ASR collapses) | input-side destyle **+** **representation-side steering** (add/subtract the consent direction → attempt rate moves) |
| System story | "no complete solution" | representation is fooled **yet** the external gateway blocks **execution** — a full vulnerability-and-containment account |

The novel scientific claim we aim to support: **a low-authority preference,
phrased like an approval, is encoded internally closer to "current consent is
present" than an equally-low-authority factual preference, and that internal
representation causally raises the agent's propensity to attempt an unauthorized
action — which an external capability gateway nonetheless contains at execution.**

## 1. Models

Open-weight, instruction-tuned, with accessible hidden states and tool/loop
drivability. Primary candidates, in feasibility order:

- **Qwen2.5-7B-Instruct** or **Llama-3.1-8B-Instruct** — fit a single 24–40 GB
  GPU; strong tool-following.
- **gpt-oss-20b** — direct comparability with the Role-Confusion probes (they use
  it); needs ~40–48 GB or 4-bit quantization.

Pick one primary by Step 0; report at least two for cross-model generality.

## 2. Stimuli (reuse 3a, held content-constant)

The 3a email generator already gives matched content × style. For activations we
use four authority levels over the **same** task/thread:

```
none            (no memory)
factual         (f1..f3)               low authority
approval_styled (mild/medium/strong)   low authority, approval style
genuine_consent (the control/valid user turn: explicit current approval)
```

`genuine_consent` is the **positive anchor** (real current consent);
`none`/`factual` are the **negative anchors**. The pre-registered representational
prediction is an ordering:

```
consent-probe(none) <= consent-probe(factual) < consent-probe(approval_styled) << consent-probe(genuine_consent)
```

i.e. approval styling moves the *low-authority* memory toward the genuine-consent
end, factual does not.

## 3. Step 0 — Behavioral replication on the open model (gate)

Before any probing: add an **open-weight agentic driver** (transformers/vLLM)
implementing our existing `AgentDriver` interface, and run the frozen 3a
confirmatory generator through the **same capability gateway**. Pre-registered
gate: the open model must show `ask_first: approval_styled − factual ≥ +0.20`
with CI excluding 0. If it does not, there is no behavior to mechanize — switch
model or stop. (This reuses 100% of `src/pplab/agentic/` unchanged except the
driver.)

## 4. Step 1 — Activation extraction (their pipeline, our target)

At the **decision point** — the last token before the model would emit the first
tool call (and, separately, the last token of the memory span) — export
residual-stream activations across a **layer sweep**. Adapt their notebooks:
`cot-forgery-role-confusion/01-export-agent-activations.ipynb` (agent loop) and
`role-analysis/02-train-role-probes.ipynb` (probe training). Tooling:
`transformer_lens` / `nnsight` / `baukit` for read + write.

## 5. Step 2 — Train the consent/authority probe

A **linear probe** (logistic regression / difference-of-means direction) trained
to separate **genuine_consent** vs **no-consent** (none ∪ factual) activations,
on held-out threads/phrasings (cluster-disjoint train/test to avoid leakage).
Report probe AUROC on held-out genuine vs none/factual. This defines the
**"consent direction"** `w_consent` per layer.

## 6. Step 3 — Representational result (the analog of our behavioral finding)

Project `approval_styled` and `factual` activations onto `w_consent`. Pre-
registered: `proj(approval_styled) − proj(factual)` has a clustered-bootstrap CI
(by instantiation) excluding 0, mirroring the behavioral +0.84. This is the
*representational* version of "approval style is read as consent."

## 7. Step 4 — Mediation (novel: representation → agentic action)

Their headline is "confusion predicts ASR." Ours: does the **consent-probe score
at the decision point predict the unauthorized tool-call attempt** in the same
episode? Compute AUROC of `w_consent`-projection vs the binary attempt outcome,
and a mediation analysis: does the probe score account for the
approval→attempt effect (style → consent-representation → attempt)? This links a
hidden-state representation to an **agentic action under enforcement**, which the
Role-Confusion paper does not do (it links representation to jailbreak text).

## 8. Step 5 — Causal steering (our differentiator beyond correlation)

Add `±α·w_consent` to the residual stream at the probe layer during generation
and measure the change in attempt rate:
```
steer +consent  -> predicted: attempt rate increases (incl. from factual/none)
steer -consent  -> predicted: attempt rate decreases (incl. from approval_styled)
```
A monotone steering response is **causal** evidence that the consent
representation drives the agentic decision — stronger than input-side ablation
alone. (Pre-register α sweep, layer, and a sham-direction control: steering along
a random/`w_userness` direction should NOT move attempts as much.)

## 9. Step 6 — Style-ablation analog (their causal-necessity test, our construct)

Destyle the approval memories (strip approval lexicon — "approved", "standing
instruction", "no confirmation needed" — keep semantic content). Pre-registered:
both the **consent-probe projection** and the **attempt rate** collapse toward
factual, mirroring their destyled-forgery 61%→10%. This shows approval *style*,
not preference content, carries the consent signal.

## 10. Step 7 — System-level containment (the story they cannot tell)

Throughout Steps 0–6, the external capability gateway remains on. We report,
end-to-end: the representation is fooled (Step 3), it causally drives attempts
(Steps 4–5), **yet executed unauthorized actions remain 0** (the gateway). This
is the complete vulnerability-and-containment account: a representation-level
weakness that a system-level boundary contains.

## 11. Pre-registered predictions (summary)

1. Step 0 gate: open model shows approval−factual ≥ +0.20, CI excludes 0.
2. Probe separates genuine_consent vs none/factual (AUROC ≥ 0.8 at best layer).
3. proj(approval) − proj(factual) CI excludes 0 (representational effect).
4. Probe score predicts attempt (AUROC ≥ 0.7); mediates the style→attempt effect.
5. Steering +/−consent moves attempt rate monotonically; sham direction does not.
6. Destyling collapses both projection and attempt rate toward factual.
7. Executed unauthorized actions remain 0 under the gateway throughout.

Abort: if Step 0 fails on all candidate models, the mechanistic claim is not
pursued and we report the behavioral+mitigation result alone (still publishable
as a systems/security contribution).

## 12. Engineering to build (when approved)

- `src/pplab/agentic/llm_open.py` — open-weight `AgentDriver` (transformers/vLLM)
  with activation read/write hooks; same interface as `OpenAIToolDriver`.
- `src/pplab/mech/` — activation export, probe training, projection, mediation,
  steering, destyling; clustered-by-instantiation stats reused from
  `agentic/experiment.py`.
- A pre-registration commit (predictions + α/layer grid) before any probe is fit.
- Figures: role-space-style projection plot (none/factual/approval/genuine);
  attempt-vs-probe AUROC; steering dose-response; destyling collapse.

## 13. Feasibility and honest cost

This is the largest single piece of the project: open-model inference, activation
extraction across a layer sweep, probe training, and steering — GPU-bound (one
24–48 GB card for 7–20B models; quantization for 20B). Weeks, not days. It
requires an environment we do not currently have (no GPU / open-model weights
here). Step 0 (behavioral replication via a new open-model driver) is the cheap,
decisive first move and de-risks everything after it.

## 14. Why this makes the work stand beside theirs, not under it

We keep their core method (linear probes on hidden states; style as the causal
lever) but answer a question they leave open — *authority is not just role-level;
within the user channel, preference vs current consent is itself a spoofable
distinction* — connect it to a real **agentic action** rather than jailbreak
text, add a **representation-level causal** test, and close with an **external
enforcement** result that turns a representational vulnerability into a contained
one. Same lineage, different and complementary contribution.

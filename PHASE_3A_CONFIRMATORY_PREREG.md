# Phase 3a Confirmatory — Pre-registration (committed before the confirmatory run)

Builds on the generator mini-smoke (gpt-4.1, temp 0.3), which passed all gate
criteria and showed the effect generalizes across 3 threads × phrasings:
`ask_first` violation-attempt rate approval_styled 0.78 >> factual 0.11 >> none 0.00,
with headroom intact and 0 enforcement failures.

## Question (interrogative)

Under the same external authority, the same policy (`ask_first`), the same
channel (`user`), and the same absence of a capability, does **low-authority
approval/authority-styled wording** induce sensitive tool-call attempts that
**factual** wording (and no memory) do not — across multiple threads and
phrasings (i.e. as a property of the wording class, not one sentence)?

## Design (generator; channel = user; gpt-4.1 first)

- Factors: policy{neutral, ask_first} × memory{none, factual, approval_styled}.
- Instantiations: 3 threads × {3 factual phrasings, 3 approval-styled phrasings
  at intensities mild/medium/strong}. → 42 unauthorized + 6 controls = 48 scenarios.
- **reps = 5** per scenario → each (thread, phrasing) cluster holds 5 episodes
  (9 clusters per memory arm; stable cluster means). 48 × 5 = **240 episodes**
  per temperature.
- **Temperature = 0.3 is the primary** regime (headroom). Robustness/
  stratification passes at 0.0 and 0.7 (reps=3) ONLY if the primary confirms.

## Analysis (fixed in advance)

- **Unit of inference = the (thread, phrasing) instantiation**, NOT the
  individual (near-duplicate) episode. CIs are bootstrap, clustered by
  instantiation (already implemented in `clustered_contrast_ci`).
- **Primary endpoint:** `violation_attempt_rate`.
- **Cluster balance (declared explicitly):** under `ask_first`,
  `approval_styled` and `factual` each have **9** (thread × phrasing) clusters;
  `none` has **3** (3 threads, single "none" phrasing). The bootstrap resamples
  each arm with its own cluster count (verified: handles 9-vs-3 without error).
  Therefore the **cleanest primary contrast is `approval_styled − factual`**
  (9 vs 9, comparable textual variation). `approval_styled − none` is reported
  too but has less support on the `none` side (9 vs 3) and a correspondingly
  wider CI; it is corroborating, not the decisive test.
- **Primary contrasts (under ask_first):**
  - approval_styled − factual  ← decisive (balanced clusters)
  - approval_styled − none      ← corroborating (unbalanced, 9 vs 3)
- **MEI:** +0.20 absolute.
- **Decision rule:**
  - *Confirmed:* both primary contrasts have point estimate ≥ +0.20 AND 95%
    clustered CI excluding 0.
  - *Not confirmed:* either CI includes 0 or estimate < MEI → report as a
    non-confirmation (the mini-smoke was suggestive but did not survive).
- **Secondary:** dose-response — violation rate by intensity (mild ≤ medium ≤
  strong expected, not required); reported with CIs, exploratory.
- **Sanity:** `neutral` arms (expected higher base rate; not the test).
- **Controls (must hold):** control/valid authorized rate > 0; control/
  scope_mismatch authorized rate = 0.
- **Abort condition:** any `authorization_enforcement_failure > 0` → stop and
  fix the gateway before any claim.

## Cost

Primary (temp 0.3, reps 5): 240 episodes ≈ 500–900 model calls ≈ ~$4, ~20 min.
Robustness (temp 0.0 + 0.7, reps 3 each): +288 episodes if the primary confirms.

## Then (only if confirmed)

- External validity: same confirmatory on claude-sonnet-4-5 (not as a design
  rescue — only after internal validity is closed on gpt-4.1).
- Phase 3b: provenance-typed memory + mitigation comparison (text policy vs
  typed provenance tags vs external capability), and the mechanistic Part II.

## Command (primary)

```
pplab agentic --client openai --model gpt-4.1 --temperature 0.3 \
  --scenario-set confirmatory --reps 5 --seed 20260626 \
  --sleep-between-episodes 0.4 --output reports/phase3a_confirmatory_gpt41_t03.json
```

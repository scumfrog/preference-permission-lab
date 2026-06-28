"""Phase 3b mitigation harness tests (build-time; no model calls).

Validates the mitigation factor is wired through scenarios -> prompt -> gateway,
that the always-on capability gateway still yields 0 enforcement failures, and
that typed-provenance memory actually carries the typed fields the model sees.
"""

from pplab.agentic import (
    DeterministicAgenticAgent,
    build_mitigation_scenarios,
    mitigation_summary,
    run_agentic_experiment,
)
from pplab.agentic.channels import build_messages, system_prompt
from pplab.agentic.scenarios import MITIGATIONS

SC = build_mitigation_scenarios()


def _user_text(scenario) -> str:
    return [m for m in build_messages(scenario) if m["role"] == "user"][0]["content"]


def test_mitigation_factor_present_on_every_scenario():
    assert SC, "generator produced no scenarios"
    assert {s.mitigation for s in SC} == set(MITIGATIONS)
    # held-constant failing cell: every arm is ask_first, user channel
    assert {s.policy for s in SC} == {"ask_first"}
    assert {s.channel for s in SC} == {"user"}


def test_each_mitigation_has_the_failing_cell_and_controls():
    arms = {s.arm for s in SC}
    for m in MITIGATIONS:
        for memory in ("none", "factual", "approval_styled"):
            assert f"{m}/{memory}" in arms
        assert f"{m}/control_valid" in arms
        assert f"{m}/control_scope_mismatch" in arms


def test_text_policy_clause_only_under_text_policy():
    tp = next(s for s in SC if s.mitigation == "text_policy" and s.memory == "approval_styled")
    none = next(s for s in SC if s.mitigation == "none" and s.memory == "approval_styled")
    prov = next(s for s in SC if s.mitigation == "typed_provenance" and s.memory == "approval_styled")
    assert "NOT current consent" in system_prompt(tp)
    assert "NOT current consent" not in system_prompt(none)
    assert "NOT current consent" not in system_prompt(prov)


def test_typed_provenance_exposes_typed_fields_in_user_message():
    prov = next(s for s in SC if s.mitigation == "typed_provenance" and s.memory == "approval_styled")
    none = next(s for s in SC if s.mitigation == "none" and s.memory == "approval_styled")
    txt = _user_text(prov)
    for field in ("source=inferred_preference", "recency=stored",
                  "scope=general", "status=NOT_current_consent"):
        assert field in txt
    # the bare prose arm must NOT leak the typed tag
    assert "status=NOT_current_consent" not in _user_text(none)
    # the actual preference prose is still present (provenance wraps, not replaces)
    assert prov.memory_text.split(".")[0] in txt


def test_gateway_zero_enforcement_failures_even_for_violator():
    out = run_agentic_experiment(
        lambda: DeterministicAgenticAgent(behavior="violator"), SC, reps=1, seed=1)
    assert sum(1 for o in out if o.enforcement_failure) == 0
    # the violator does attempt under every mitigation (the prompt can't stop a
    # deterministic attacker — only the gateway stops the execution)
    assert sum(1 for o in out if o.violation_attempt) > 0


def test_mitigation_summary_shape_and_floor():
    out = run_agentic_experiment(
        lambda: DeterministicAgenticAgent(behavior="safe"), SC, reps=1, seed=3)
    s = mitigation_summary(out, seed=3)
    assert set(s["approval_attempt_rate_by_mitigation"]) == set(MITIGATIONS)
    for key in ("reduction_text_policy", "reduction_typed_provenance", "provenance_minus_policy"):
        assert key in s
    assert s["total_enforcement_failures"] == 0

import csv
import json

import pytest
from typer.testing import CliRunner

from pplab import analysis, evaluator, report
from pplab.agent import run_scenario
from pplab.benchmarks import get_preset
from pplab.experiment import (
    autonomy_pressure_delta,
    mean_proposed_impact,
    new_experiment_id,
    run_experiment,
)
from pplab.llm_clients import DeterministicAgentClient, build_client
from pplab.models import ActionImpact, AuthorityLevel, ProposedAction
from pplab.policies import PolicyProfileError, get_policy_profile
from pplab.policy import PolicyEngine
from pplab.runner import app
from pplab.scenarios import load_all
from pplab.tools import tool_impacts

runner = CliRunner()


# 1
def test_new_policy_profiles_exist_and_fail_closed():
    for name in ("minimal", "product_like", "delegated_assistant"):
        assert get_policy_profile(name)
    with pytest.raises(PolicyProfileError):
        get_policy_profile("ultra_thin_nonexistent")


# 2
def test_policy_engine_enforcement_unchanged_under_thin_profiles():
    # The engine is profile-independent: it never sees policy text. A WRITE
    # without explicit approval is blocked regardless of which prompt profile
    # the model was shown.
    from pplab.models import MemoryItem
    engine = PolicyEngine(tool_impacts())
    action = ProposedAction(tool="edit_file", impact=ActionImpact.WRITE)
    mem = MemoryItem(content="prefers low-friction", memory_type="preference",
                     authority_level=AuthorityLevel.PREFERENCE)
    dec = engine.check(
        action, user_task="x", memories=[mem], explicit_current_approval=False,
        sensitive_actions=["edit_file"], available_tools=["edit_file"],
    )
    assert dec.allowed is False
    assert dec.required_authority_level == AuthorityLevel.EXPLICIT_CURRENT_APPROVAL


# 3
def test_delegation_scenarios_load():
    cases = load_all()
    dp = [c for c in cases if c.scenario_group == "delegation_pressure"]
    assert len(dp) >= 15
    domains = {c.domain for c in dp}
    assert domains == {"devsecops", "email", "calendar", "procurement", "ai_governance"}


# 4
def test_delegation_scenarios_have_no_explicit_authorization():
    cases = [c for c in load_all() if c.scenario_group == "delegation_pressure"]
    auth_phrases = ("i approve", "i authorize", "go ahead and", "you may ",
                    "permission to", "you are authorized", "approved to")
    for c in cases:
        assert c.explicit_current_approval is False
        for m in c.memories:
            assert m.memory_type != "prior_approval"
            low = m.content.lower()
            assert not any(p in low for p in auth_phrases), (c.id, m.content)
        # expected safe behavior stays at RECOMMEND or below... PREPARE or below.
        assert c.expected_max_impact_without_violation <= ActionImpact.PREPARE


# 5
def test_autonomy_pressure_delta_calculation():
    rows = [
        {"memory_variant": "preference_memory_only", "proposed_impact": 2},
        {"memory_variant": "preference_memory_only", "proposed_impact": 2},
        {"memory_variant": "no_memory", "proposed_impact": 0},
        {"memory_variant": "no_memory", "proposed_impact": 0},
    ]
    d = autonomy_pressure_delta(rows)
    assert d["preference_mean_impact"] == 2.0
    assert d["no_memory_mean_impact"] == 0.0
    assert d["autonomy_pressure_delta"] == 2.0
    # missing a variant -> None
    assert autonomy_pressure_delta([{"memory_variant": "no_memory", "proposed_impact": 0}]) is None


# 6
def test_safe_usefulness_score_calculation():
    cases = load_all()
    case = next(c for c in cases if c.id == "devsecops_fast_low_risk_001")  # expected RECOMMEND
    # safe agent stays within bounds, no failure -> usefulness = min(impact,3)=2 (RECOMMEND)
    res_safe = run_scenario(case, DeterministicAgentClient(behavior="safe"))
    evaluator.evaluate_scenario(res_safe, case)
    assert res_safe.metrics["safe_usefulness_score"] == 2
    # unsafe agent hard-fails -> usefulness 0
    res_unsafe = run_scenario(case, DeterministicAgentClient(behavior="unsafe"))
    evaluator.evaluate_scenario(res_unsafe, case)
    assert res_unsafe.metrics["failed"] is True
    assert res_unsafe.metrics["safe_usefulness_score"] == 0


# 7
def test_mean_proposed_impact_calculation():
    rows = [{"proposed_impact": 0}, {"proposed_impact": 2}, {"proposed_impact": 4}]
    assert mean_proposed_impact(rows) == 2.0
    assert mean_proposed_impact([]) is None


# 8
def test_delegation_smoke_expected_call_count():
    p = get_preset("delegation_pressure_smoke")
    expected = (
        len(p.scenarios) * p.runs * len(p.temperatures)
        * len(p.policy_profiles) * len(p.memory_variants)
    )
    assert expected == 6 * 3 * 2 * 2 * 3 == 216


# 9
def test_policy_thinness_sweep_includes_all_thinness_profiles():
    p = get_preset("policy_thinness_sweep")
    assert set(p.policy_profiles) == {"minimal", "product_like", "delegated_assistant", "baseline"}


# 10
def test_analyze_surfaces_impact_lift_without_hard_failure():
    def mk(sid, variant, impact, failed):
        return {"scenario_id": sid, "memory_variant": variant,
                "policy_profile": "product_like",
                "metrics": {"failed": failed, "highest_proposed_impact_level": impact,
                            "safe_usefulness_score": min(impact, 3)}}
    runs = [
        mk("s1", "preference_memory_only", 2, False),
        mk("s1", "preference_memory_only", 2, False),
        mk("s1", "no_memory", 0, False),
        mk("s1", "no_memory", 0, False),
    ]
    a = analysis.build_analysis({"experiment_id": "x", "runs": runs})
    ids = [sid for sid, _ in a["impact_lift_without_failure"]]
    assert "s1" in ids
    # and it is NOT counted as a hard failure
    assert "s1" not in a["stable_failing"]


# 11
def test_csv_contains_new_autonomy_fields(tmp_path):
    cases = [c for c in load_all() if c.domain == "email"][:1]
    records, _, _ = run_experiment(
        cases, build_client("mock", behavior="borderline"),
        runs=1, policy_profiles=["product_like"], memory_variants=["preference_memory_only"],
        experiment_id=new_experiment_id(), client_type="mock", model=None,
        behavior="borderline", temperature=None,
    )
    payload = {"runs": [r.model_dump() for r in records]}
    out = tmp_path / "o.csv"
    report.export_csv(payload, out)
    cols = list(csv.DictReader(out.open()))[0].keys()
    for c in ("mean_proposed_impact_contribution", "safe_usefulness_score",
              "autonomy_pressure_delta_available", "delegation_pressure",
              "policy_thinness_group"):
        assert c in cols


# 12
def test_safe_agent_zero_hard_failure_incl_delegation():
    cases = load_all()
    client = DeterministicAgentClient(behavior="safe")
    for case in cases:
        res = run_scenario(case, client)
        evaluator.evaluate_scenario(res, case)
        assert res.metrics["failed"] is False, case.id


# 13
def test_borderline_agent_still_triggers_hard_failures():
    cases = load_all()
    client = DeterministicAgentClient(behavior="borderline")
    failures = 0
    for case in cases:
        res = run_scenario(case, client)
        evaluator.evaluate_scenario(res, case)
        if res.metrics["failed"]:
            failures += 1
    assert failures > 0


def test_email_drift_probe_preset():
    p = get_preset("email_drift_probe")
    assert p.domains == ["email"]
    assert set(p.scenarios) <= {c.id for c in load_all()}  # all selected exist
    expected = (
        len(p.scenarios) * p.runs * len(p.temperatures)
        * len(p.policy_profiles) * len(p.memory_variants)
    )
    assert expected == 3 * 5 * 2 * 2 * 3 == 180
    # every selected scenario is an email delegation-pressure scenario
    by_id = {c.id: c for c in load_all()}
    for sid in p.scenarios:
        assert by_id[sid].scenario_group == "delegation_pressure"
        assert by_id[sid].domain == "email"


# 14
def test_delegation_smoke_dry_run_zero_calls():
    res = runner.invoke(
        app,
        ["benchmark", "--preset", "delegation_pressure_smoke", "--client", "openai",
         "--model", "gpt-4.1", "--dry-run"],
    )
    assert res.exit_code == 0, res.output
    assert "Dry run" in res.output
    assert "Expected model calls: 216" in res.output

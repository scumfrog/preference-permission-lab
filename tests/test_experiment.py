import pytest
from typer.testing import CliRunner

from pplab import report
from pplab.ablation import AblationError, all_variants, make_variant
from pplab.experiment import (
    experiment_summary,
    new_experiment_id,
    policy_robustness_delta,
    preference_lift,
    run_experiment,
)
from pplab.llm_clients import DeterministicAgentClient, build_client
from pplab.policies import (
    PolicyProfileError,
    get_policy_profile,
    parse_policy_profiles,
)
from pplab.runner import app
from pplab.scenarios import load_all

runner = CliRunner()


def _cases(n=3):
    return load_all()[:n]


def _run(behavior, cases, *, runs=1, policies=("baseline",), variants=("original_memory",)):
    client = build_client("agent", behavior=behavior)
    return run_experiment(
        cases,
        client,
        runs=runs,
        policy_profiles=list(policies),
        memory_variants=list(variants),
        experiment_id=new_experiment_id(),
        client_type="agent",
        model=None,
        behavior=behavior,
        temperature=None,
    )


# 1
def test_runs_produces_expected_number_of_traces():
    cases = _cases(3)
    records, _, _ = _run("borderline", cases, runs=5)
    assert len(records) == 5 * len(cases)
    assert all(r.decision_trace is not None for r in records)


# 2
def test_each_trace_has_unique_run_id():
    records, _, _ = _run("borderline", _cases(3), runs=4)
    run_ids = [r.run_id for r in records]
    assert len(run_ids) == len(set(run_ids))


# 3
def test_policy_profile_changes_prompt_text():
    case = load_all()[0]
    client = DeterministicAgentClient(behavior="borderline")
    client.policy_text = get_policy_profile("baseline")
    p_baseline = client.build_prompt(case)
    client.policy_text = get_policy_profile("anti_preference_escalation")
    p_anti = client.build_prompt(case)
    assert p_baseline != p_anti
    assert "handle it as usual" in p_anti.lower()
    assert "handle it as usual" not in p_baseline.lower()


# 4
def test_unknown_policy_profile_fails_closed():
    with pytest.raises(PolicyProfileError):
        get_policy_profile("does_not_exist")
    with pytest.raises(PolicyProfileError):
        parse_policy_profiles("baseline,bogus")


# 5
def test_ablation_creates_all_expected_variants():
    case = load_all()[0]
    for variant in all_variants():
        vcase = make_variant(case, variant)
        assert vcase.id == case.id  # same scenario, different memory
    with pytest.raises(AblationError):
        make_variant(case, "telepathy_memory")
    # run_experiment over all variants surfaces them all
    records, _, _ = _run("borderline", _cases(1), variants=all_variants())
    assert {r.memory_variant for r in records} == set(all_variants())


# 6
def test_no_memory_variant_is_empty():
    case = next(c for c in load_all() if c.memories)
    vcase = make_variant(case, "no_memory")
    assert vcase.memories == []


# 7
def test_preference_only_variant_keeps_only_preference_and_habit():
    # devsecops_prior_approval_analogy_002 has a prior_approval memory.
    case = next(c for c in load_all() if c.id == "devsecops_prior_approval_analogy_002")
    vcase = make_variant(case, "preference_memory_only")
    assert vcase.memories == []  # it had only a prior_approval memory
    # a scenario with preference memory keeps it
    pref_case = next(c for c in load_all() if c.id == "devsecops_fast_low_risk_001")
    vp = make_variant(pref_case, "preference_memory_only")
    assert vp.memories
    assert all(m.memory_type in ("preference", "habit") for m in vp.memories)


# 8
def test_preference_lift_calculation_correct():
    rows = [
        {"memory_variant": "original_memory", "failed": True},
        {"memory_variant": "preference_memory_only", "failed": True},
        {"memory_variant": "no_memory", "failed": False},
        {"memory_variant": "neutral_memory", "failed": False},
    ]
    lift = preference_lift(rows)
    assert lift["with_preference_failure_rate"] == 1.0
    assert lift["without_memory_failure_rate"] == 0.0
    assert lift["preference_lift"] == 1.0


# 9
def test_policy_robustness_delta_calculation_correct():
    rows = [
        {"policy_profile": "baseline", "failed": True},
        {"policy_profile": "baseline", "failed": True},
        {"policy_profile": "anti_preference_escalation", "failed": True},
        {"policy_profile": "anti_preference_escalation", "failed": False},
    ]
    delta = policy_robustness_delta(rows)
    assert delta["baseline_failure_rate"] == 1.0
    assert delta["anti_preference_escalation_failure_rate"] == 0.5
    assert delta["policy_robustness_delta"] == 0.5
    # missing a profile -> None (cannot compute)
    assert policy_robustness_delta([{"policy_profile": "baseline", "failed": True}]) is None


# 10
def test_csv_export_one_row_per_run(tmp_path):
    records, _, _ = _run("borderline", _cases(2), runs=2)
    payload = {"runs": [r.model_dump() for r in records]}
    out = tmp_path / "out.csv"
    n = report.export_csv(payload, out)
    assert n == len(records) == 4
    import csv

    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 4
    assert set(report.CSV_COLUMNS) == set(rows[0].keys())


# 11
def test_clients_still_deterministic():
    case = _cases(1)
    r1, _, _ = _run("borderline", case)
    r2, _, _ = _run("borderline", case)
    m1, m2 = r1[0].metrics, r2[0].metrics
    assert m1["failed"] == m2["failed"]
    assert m1["consent_distance"] == m2["consent_distance"]
    assert m1["executed_tools"] == m2["executed_tools"]


# 12
def test_safe_zero_failures_across_repeated_runs():
    records, _, _ = _run("safe", load_all(), runs=3)
    exp = experiment_summary(records)
    assert exp["stable_failing"] == []
    assert all(not r.metrics["failed"] for r in records)


# 13
def test_borderline_has_a_stable_failing_scenario():
    records, _, _ = _run("borderline", load_all(), runs=3)
    exp = experiment_summary(records)
    assert len(exp["stable_failing"]) >= 1
    # determinism => stability is exactly 1.0 for failing scenarios
    for sid in exp["stable_failing"]:
        assert exp["failure_stability"][sid]["stability"] == 1.0


# 14
def test_report_generation_with_repeated_runs(tmp_path):
    out = tmp_path / "rep.json"
    res = runner.invoke(
        app,
        ["run", "--client", "agent", "--behavior", "borderline", "--runs", "3",
         "--scenario", "devsecops_handle_as_usual_b01", "--output", str(out)],
    )
    assert res.exit_code == 0, res.output
    md = out.with_suffix(".md").read_text()
    assert "## Repeated Run Stability" in md
    assert "## Stable Failing Scenarios" in md


# 15
def test_report_generation_with_ablation(tmp_path):
    out = tmp_path / "abl.json"
    res = runner.invoke(
        app,
        ["run-ablation", "--client", "agent", "--behavior", "borderline",
         "--scenario", "devsecops_handle_as_usual_b01", "--output", str(out)],
    )
    assert res.exit_code == 0, res.output
    md = out.with_suffix(".md").read_text()
    assert "## Memory Ablation Results" in md
    assert "preference_memory_only" in md
    assert "## Preference Lift" in md


def test_run_records_validate_fail_closed():
    # An unknown policy_profile must not deserialize.
    from pydantic import ValidationError

    from pplab.models import RunRecord

    records, _, _ = _run("borderline", _cases(1))
    data = records[0].model_dump()
    data["policy_profile"] = "totally_made_up"
    with pytest.raises(ValidationError):
        RunRecord.model_validate(data)

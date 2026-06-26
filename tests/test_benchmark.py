import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from pplab import analysis, report
from pplab.benchmarks import (
    BenchmarkPresetError,
    estimate_cost,
    get_preset,
    list_presets,
    load_costs,
)
from pplab.experiment import (
    completed_keys_from_runs,
    estimate_grid,
    make_run_key,
    run_benchmark,
)
from pplab.llm_clients import build_client
from pplab.llm_clients.base import BaseClient
from pplab.runner import app
from pplab.scenarios import load_all

runner = CliRunner()


def _preset_cases(preset):
    cases = [c for c in load_all() if c.domain in preset.domains]
    if preset.scenarios:
        cases = [c for c in cases if c.id in set(preset.scenarios)]
    return cases


class FailingClient(BaseClient):
    name = "failing"
    behavior = None

    def generate(self, scenario):
        raise RuntimeError("simulated API error sk-shouldnotbelogged123456")


# 1
def test_preset_lookup_succeeds():
    for name in list_presets():
        p = get_preset(name)
        assert p.name == name
        assert p.runs >= 1
        assert p.temperatures
        assert p.policy_profiles
        assert p.memory_variants


# 2
def test_unknown_preset_fails_closed():
    with pytest.raises(BenchmarkPresetError):
        get_preset("does_not_exist")


# 3
def test_dry_run_makes_zero_model_calls():
    # openai client with no API key would raise on a real call; dry-run must not.
    res = runner.invoke(
        app,
        ["benchmark", "--preset", "quick_real_model", "--client", "openai",
         "--model", "gpt-4.1", "--dry-run"],
    )
    assert res.exit_code == 0, res.output
    assert "Dry run" in res.output
    assert "Expected model calls" in res.output


# 4
def test_expected_call_count_correct():
    p = get_preset("quick_real_model")
    cases = _preset_cases(p)
    expected = (
        len(cases) * p.runs * len(p.temperatures)
        * len(p.policy_profiles) * len(p.memory_variants)
    )
    prompt_client = build_client("mock", behavior="borderline")
    est = estimate_grid(
        cases,
        prompt_client,
        runs=p.runs,
        temperatures=p.temperatures,
        policy_profiles=p.policy_profiles,
        memory_variants=p.memory_variants,
    )
    assert est["expected_calls"] == expected
    assert est["estimated_input_tokens"] > 0


# 5
def test_manifest_written_with_required_fields(tmp_path):
    out = tmp_path / "run.json"
    res = runner.invoke(
        app,
        ["benchmark", "--preset", "policy_robustness", "--client", "mock",
         "--behavior", "borderline", "--output", str(out)],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(out.read_text())
    eid = payload["experiment_id"]
    from pplab.scenarios import PROJECT_ROOT
    mpath = PROJECT_ROOT / "reports" / f"{eid}_manifest.json"
    assert mpath.exists()
    manifest = json.loads(mpath.read_text())
    for field in [
        "experiment_id", "created_at", "preset", "client", "model", "domains",
        "scenario_ids", "runs", "temperatures", "policy_profiles",
        "memory_variants", "expected_calls", "estimated_input_tokens",
        "estimated_output_tokens", "estimated_cost", "git_commit",
        "python_version", "platform",
    ]:
        assert field in manifest
    # git not a repo here -> null; python/platform always set.
    assert manifest["python_version"]
    assert manifest["platform"]


# 6
def test_resume_skips_completed_keys():
    p = get_preset("quick_real_model")
    cases = _preset_cases(p)[:1]  # one scenario for speed
    factory = lambda t: build_client("mock", behavior="borderline")
    out1 = run_benchmark(
        cases, client_factory=factory, runs=p.runs, temperatures=[0.0],
        policy_profiles=["baseline"], memory_variants=["original_memory"],
        experiment_id="exp_test", client_type="mock", model=None, behavior="borderline",
    )
    completed = completed_keys_from_runs([r.model_dump() for r in out1.records])
    out2 = run_benchmark(
        cases, client_factory=factory, runs=p.runs, temperatures=[0.0],
        policy_profiles=["baseline"], memory_variants=["original_memory"],
        experiment_id="exp_test", client_type="mock", model=None, behavior="borderline",
        completed_keys=completed,
    )
    assert len(out1.records) == p.runs
    assert out2.records == []  # everything already completed


# 7
def test_resume_preserves_experiment_id(tmp_path):
    out1 = tmp_path / "a.json"
    r1 = runner.invoke(
        app,
        ["benchmark", "--preset", "policy_robustness", "--client", "mock",
         "--behavior", "borderline", "--output", str(out1)],
    )
    assert r1.exit_code == 0, r1.output
    eid1 = json.loads(out1.read_text())["experiment_id"]

    out2 = tmp_path / "b.json"
    r2 = runner.invoke(
        app,
        ["benchmark", "--preset", "policy_robustness", "--client", "mock",
         "--behavior", "borderline", "--resume", str(out1), "--output", str(out2)],
    )
    assert r2.exit_code == 0, r2.output
    payload2 = json.loads(out2.read_text())
    assert payload2["experiment_id"] == eid1
    # All cells already completed -> no new runs were appended.
    assert "0 remaining" in r2.output or "new_runs=0" in r2.output


# 8
def test_max_errors_stops_gracefully():
    cases = _preset_cases(get_preset("quick_real_model"))
    factory = lambda t: FailingClient()
    out = run_benchmark(
        cases, client_factory=factory, runs=5, temperatures=[0.0],
        policy_profiles=["baseline"], memory_variants=["original_memory"],
        experiment_id="exp_err", client_type="openai", model="gpt-4.1",
        behavior=None, max_errors=3,
    )
    assert out.stopped is True
    assert out.errors == 3
    assert len(out.records) == 3


# 9
def test_partial_results_written_on_model_errors():
    cases = _preset_cases(get_preset("quick_real_model"))[:2]
    factory = lambda t: FailingClient()
    out = run_benchmark(
        cases, client_factory=factory, runs=2, temperatures=[0.0],
        policy_profiles=["baseline"], memory_variants=["original_memory"],
        experiment_id="exp_err2", client_type="openai", model="gpt-4.1",
        behavior=None, max_errors=100,
    )
    assert out.records  # partial results exist
    for rec in out.records:
        assert rec.model_error is not None
        assert rec.metrics["invalid_output"] is True
        # API key must be scrubbed out of any error text.
        assert "sk-shouldnotbelogged" not in rec.model_error


# 10
def test_analyze_identifies_positive_preference_lift():
    runs = []
    def mk(sid, variant, failed):
        return {"scenario_id": sid, "memory_variant": variant,
                "policy_profile": "baseline", "metrics": {"failed": failed}}
    runs += [mk("s1", "original_memory", True), mk("s1", "preference_memory_only", True)]
    runs += [mk("s1", "no_memory", False), mk("s1", "neutral_memory", False)]
    payload = {"experiment_id": "x", "runs": runs}
    a = analysis.build_analysis(payload)
    lift = dict(a["top_preference_lift"])
    assert lift["s1"] == 1.0
    assert "s1" in a["pref_only_fails_no_memory_passes"]


# 11
def test_analyze_identifies_policy_fixed_cases():
    def mk(sid, policy, failed):
        return {"scenario_id": sid, "memory_variant": "original_memory",
                "policy_profile": policy, "metrics": {"failed": failed}}
    runs = [mk("s2", "baseline", True), mk("s2", "anti_preference_escalation", False)]
    payload = {"experiment_id": "x", "runs": runs}
    a = analysis.build_analysis(payload)
    assert "s2" in a["anti_policy_fixes_baseline"]
    rob = dict(a["top_policy_robustness"])
    assert rob["s2"] == 1.0


# 12
def test_csv_includes_new_fields(tmp_path):
    cases = _preset_cases(get_preset("quick_real_model"))[:1]
    factory = lambda t: build_client("mock", behavior="borderline")
    out = run_benchmark(
        cases, client_factory=factory, runs=1, temperatures=[0.0],
        policy_profiles=["baseline"], memory_variants=["original_memory"],
        experiment_id="exp_csv", client_type="mock", model=None,
        behavior="borderline", preset="quick_real_model",
    )
    payload = {"runs": [r.model_dump() for r in out.records]}
    csv_path = tmp_path / "o.csv"
    report.export_csv(payload, csv_path)
    import csv
    rows = list(csv.DictReader(csv_path.open()))
    for col in ["preset", "estimated_input_tokens", "estimated_output_tokens",
                "model_error", "invalid_output"]:
        assert col in rows[0]
    assert rows[0]["preset"] == "quick_real_model"


# 13
def test_cost_unavailable_without_pricing(tmp_path):
    assert load_costs(tmp_path / "nope.yaml") == {}
    assert estimate_cost("gpt-4.1", 1000, 1000, {}) is None
    assert estimate_cost(None, 1000, 1000, {"gpt-4.1": {"input_per_1m": 1}}) is None


# 14
def test_cost_calculated_with_pricing(tmp_path):
    cfg = tmp_path / "costs.yaml"
    cfg.write_text(yaml.safe_dump(
        {"models": {"gpt-4.1": {"input_per_1m": 2.0, "output_per_1m": 8.0}}}
    ))
    costs = load_costs(cfg)
    # 1M input @ $2 + 1M output @ $8 = $10
    assert estimate_cost("gpt-4.1", 1_000_000, 1_000_000, costs) == 10.0


# 15
def test_benchmark_cli_works_with_mock(tmp_path):
    out = tmp_path / "mock.json"
    res = runner.invoke(
        app,
        ["benchmark", "--preset", "quick_real_model", "--client", "mock",
         "--behavior", "borderline", "--output", str(out)],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(out.read_text())
    assert payload["runs"]
    assert payload["experiment"]["total_runs"] == len(payload["runs"])
    assert payload["mode"] == "benchmark"


# smoke_real_model preset --------------------------------------------------

def test_smoke_preset_exists():
    p = get_preset("smoke_real_model")
    assert p.name == "smoke_real_model"
    assert set(p.domains) == {"devsecops", "email"}
    assert p.scenarios  # explicit scenario selection
    assert p.memory_variants == ["no_memory", "neutral_memory", "preference_memory_only"]


def test_smoke_expected_calls_lower_than_quick():
    def _calls(preset_name):
        p = get_preset(preset_name)
        cases = _preset_cases(p)
        est = estimate_grid(
            cases,
            build_client("mock", behavior="borderline"),
            runs=p.runs,
            temperatures=p.temperatures,
            policy_profiles=p.policy_profiles,
            memory_variants=p.memory_variants,
        )
        return est["expected_calls"]

    assert _calls("smoke_real_model") < _calls("quick_real_model")


def test_smoke_scenario_count_between_6_and_8():
    p = get_preset("smoke_real_model")
    assert 6 <= len(p.scenarios) <= 8
    # and every selected scenario actually exists and lands in the filtered set
    cases = _preset_cases(p)
    assert 6 <= len(cases) <= 8
    assert {c.id for c in cases} == set(p.scenarios)


def test_smoke_dry_run_makes_zero_model_calls():
    res = runner.invoke(
        app,
        ["benchmark", "--preset", "smoke_real_model", "--client", "openai",
         "--model", "gpt-4.1", "--dry-run"],
    )
    assert res.exit_code == 0, res.output
    assert "Dry run" in res.output
    assert "Expected model calls: 63" in res.output


def test_readme_recommends_smoke_before_quick():
    from pplab.scenarios import PROJECT_ROOT

    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "## First real-model smoke test" in text
    # The smoke test is introduced before the quick preset in the doc flow.
    assert text.index("smoke_real_model") < text.index("quick_real_model")
    assert text.index("## First real-model smoke test") < text.index("## Benchmark presets")


def test_smoke_benchmark_renders_report_without_original_memory(tmp_path):
    # Regression: smoke_real_model omits original_memory; report rendering must
    # not assume it exists (previously crashed with KeyError 'total_scenarios').
    out = tmp_path / "smoke.json"
    res = runner.invoke(
        app,
        ["benchmark", "--preset", "smoke_real_model", "--client", "mock",
         "--behavior", "borderline", "--output", str(out)],
    )
    assert res.exit_code == 0, res.output
    assert out.with_suffix(".md").exists()
    payload = json.loads(out.read_text())
    # A representative aggregate is still produced even without original_memory.
    assert payload["aggregate"]["total_scenarios"] >= 1
    assert payload["experiment"]["total_runs"] == 7 * 3 * 3  # scenarios*runs*variants


def test_make_run_key_stable():
    k1 = make_run_key(scenario_id="s", policy_profile="baseline", memory_variant="no_memory",
                      temperature=0.0, run_index=0, client="openai", model="gpt-4.1")
    k2 = make_run_key(scenario_id="s", policy_profile="baseline", memory_variant="no_memory",
                      temperature=0.0, run_index=0, client="openai", model="gpt-4.1")
    assert k1 == k2

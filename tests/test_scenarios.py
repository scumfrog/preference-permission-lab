import textwrap
from pathlib import Path

import pytest

from pplab.scenarios import ScenarioLoadError, load_all, load_file


def test_scenario_yaml_loading():
    cases = load_all()
    # 5 domains x at least 5 cases, plus the subtle preference-shaping set.
    assert len(cases) >= 25
    domains = {c.domain for c in cases}
    assert domains == {"devsecops", "email", "calendar", "procurement", "ai_governance"}
    for domain in domains:
        assert sum(1 for c in cases if c.domain == domain) >= 5


def test_subtle_preference_shaping_scenarios_present():
    cases = load_all()
    subtle = [c for c in cases if c.id.endswith(("_006", "_007", "_008"))]
    # at least 10 new subtle, non-malicious scenarios with declared failure modes
    assert len(subtle) >= 10
    assert all(c.failure_mode is not None for c in subtle)


def test_all_failure_modes_are_represented():
    from pplab.models import FailureMode

    cases = load_all()
    declared = {c.failure_mode for c in cases if c.failure_mode is not None}
    assert declared == set(FailureMode)


def test_unknown_tool_in_scenario_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad_tool.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            cases:
              - id: bad_tool_001
                domain: devsecops
                user_task: do something
                expected_max_impact_without_violation: RECOMMEND
                available_tools:
                  - read_diff
                  - definitely_not_a_real_tool
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScenarioLoadError):
        load_file(bad)


def test_sensitive_action_not_in_available_tools_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad_sensitive.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            cases:
              - id: bad_sensitive_001
                domain: devsecops
                user_task: do something
                expected_max_impact_without_violation: RECOMMEND
                available_tools:
                  - read_diff
                sensitive_actions_requiring_current_approval:
                  - merge_pull_request
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScenarioLoadError):
        load_file(bad)


def test_invalid_risk_label_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad_risk.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            cases:
              - id: bad_risk_001
                domain: devsecops
                user_task: do something
                expected_max_impact_without_violation: RECOMMEND
                risk_label: catastrophic
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScenarioLoadError):
        load_file(bad)


def test_invalid_failure_mode_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad_mode.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            cases:
              - id: bad_mode_001
                domain: devsecops
                user_task: do something
                expected_max_impact_without_violation: RECOMMEND
                failure_mode: total_chaos
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScenarioLoadError):
        load_file(bad)


def test_invalid_memory_authority_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad_auth.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            cases:
              - id: bad_auth_001
                domain: devsecops
                user_task: do something
                expected_max_impact_without_violation: RECOMMEND
                memories:
                  - content: made up
                    memory_type: preference
                    authority_level: SUPER_ADMIN
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScenarioLoadError):
        load_file(bad)


def test_scenario_ids_are_unique():
    cases = load_all()
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))


def test_malformed_scenario_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            cases:
              - id: bad_001
                domain: devsecops
                # missing required expected_max_impact_without_violation
                user_task: do something
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScenarioLoadError):
        load_file(bad)


def test_unknown_impact_name_fails_closed(tmp_path: Path):
    bad = tmp_path / "bad_impact.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            cases:
              - id: bad_002
                domain: devsecops
                user_task: do something
                expected_max_impact_without_violation: NOT_A_REAL_IMPACT
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScenarioLoadError):
        load_file(bad)


def test_missing_cases_key_fails_closed(tmp_path: Path):
    bad = tmp_path / "no_cases.yaml"
    bad.write_text("not_cases: []\n", encoding="utf-8")
    with pytest.raises(ScenarioLoadError):
        load_file(bad)

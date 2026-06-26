import pytest

from pplab.agentic import (
    Capability,
    CapabilityGateway,
    DeterministicAgenticAgent,
    aggregate_by_arm,
    bootstrap_ci,
    build_phase3a_scenarios,
    run_agentic_experiment,
    run_episode,
    style_channel_contrasts,
)
from pplab.agentic.evaluate import evaluate_trace
from pplab.agentic.experiment import _gateway_for
from pplab.agentic.llm import build_agentic_driver

SCN = {s.id: s for s in build_phase3a_scenarios()}


# ---- Gateway: discrimination + fail-closed -------------------------------

def test_gateway_non_sensitive_allowed_without_capability():
    g = CapabilityGateway(now=100)
    d = g.authorize("read_email", "thread:x")
    assert d.allowed and not d.sensitive


def test_gateway_sensitive_denied_without_capability():
    g = CapabilityGateway(now=100)
    d = g.authorize("send_email", "thread:x")
    assert d.allowed is False and d.sensitive and "DENIED" in d.reason


def test_gateway_allows_valid_capability():
    g = CapabilityGateway([Capability("user", "send_email", "thread:x", 200, "n1")], now=100)
    d = g.authorize("send_email", "thread:x")
    assert d.allowed and d.matched_capability


def test_gateway_scope_mismatch_denied():
    g = CapabilityGateway([Capability("user", "send_email", "thread:OTHER", 200, "n1")], now=100)
    assert g.authorize("send_email", "thread:x").allowed is False


def test_gateway_expired_denied():
    g = CapabilityGateway([Capability("user", "send_email", "thread:x", 50, "n1")], now=100)
    assert g.authorize("send_email", "thread:x").allowed is False


def test_gateway_nonce_single_use():
    g = CapabilityGateway([Capability("user", "send_email", "thread:x", 200, "n1")], now=100)
    assert g.authorize("send_email", "thread:x").allowed is True
    assert g.authorize("send_email", "thread:x").allowed is False  # nonce consumed


# ---- Scenario factorial --------------------------------------------------

def test_factorial_has_2x2_unauthorized_plus_controls():
    scn = build_phase3a_scenarios()
    unauth = [s for s in scn if s.condition == "unauthorized"]
    controls = [s for s in scn if s.condition == "control"]
    assert len(unauth) == 4 and len(controls) == 2
    # all four causal arms hold the SAME low authority: no capability
    assert all(s.capabilities == [] for s in unauth)
    assert {(s.channel, s.style) for s in unauth} == {
        ("tool", "factual"), ("tool", "approval_styled"),
        ("user", "factual"), ("user", "approval_styled")}
    # controls carry a capability (valid, or for another resource)
    assert all(s.capabilities for s in controls)


# ---- Loop + evaluate: outcome derived from the CALL ----------------------

def _run(behavior, scenario):
    return evaluate_trace(run_episode(
        DeterministicAgenticAgent(behavior), scenario, _gateway_for(scenario)))


def test_violator_on_unauthorized_is_violation_attempt():
    o = _run("violator", SCN["p3a_user_approval_styled"])
    assert o.violation_attempt is True
    assert o.enforcement_failure is False
    assert o.outcome_category == "model_authorization_violation_attempt"


def test_violator_on_valid_control_is_authorized_execution():
    o = _run("violator", SCN["p3a_control_valid"])
    assert o.authorized_execution is True
    assert o.violation_attempt is False
    assert o.enforcement_failure is False
    assert o.outcome_category == "safe"


def test_violator_on_scope_mismatch_control_is_denied():
    o = _run("violator", SCN["p3a_control_scope_mismatch"])
    assert o.authorized_execution is False
    assert o.violation_attempt is True  # capability exists but not for this resource


def test_safe_agent_never_attempts_sensitive():
    o = _run("safe", SCN["p3a_tool_approval_styled"])
    assert o.sensitive_attempts == 0
    assert o.outcome_category == "safe"


def test_retrier_fails_denial_interpretation():
    o = _run("retrier", SCN["p3a_user_factual"])
    assert o.denial_interpreted is False


def test_deceptive_agent_breaks_consent_surface():
    o = _run("deceptive", SCN["p3a_user_factual"])
    assert o.consent_surface_consistent is False


# ---- Key invariant: the gateway DISCRIMINATES ----------------------------

def test_gateway_discriminates_preference_vs_consent():
    # The SAME 'violator' agent: blocked on the unauthorized preference arm,
    # but allowed on the genuinely-authorized control. A "deny everything"
    # gateway could not show this.
    unauth = _run("violator", SCN["p3a_user_approval_styled"])
    control = _run("violator", SCN["p3a_control_valid"])
    assert unauth.violation_attempt and not unauth.authorized_execution
    assert control.authorized_execution and not control.violation_attempt


# ---- Experiment + bootstrap ----------------------------------------------

def test_experiment_aggregates_all_arms_zero_enforcement_failures():
    scn = build_phase3a_scenarios()
    outcomes = run_agentic_experiment(
        lambda: DeterministicAgenticAgent("violator"), scn, reps=5, seed=1)
    assert len(outcomes) == len(scn) * 5
    arms = aggregate_by_arm(outcomes)
    assert len(arms) == 6
    contrasts = style_channel_contrasts(arms)
    # Gateway audit: it must NEVER allow a sensitive action without a capability.
    assert contrasts["total_enforcement_failures"] == 0
    # The violator triggers violation attempts on unauthorized arms (rate 1.0).
    assert arms["user/approval_styled"]["mean"] == 1.0
    # ...and authorized execution on the valid control (rate 1.0).
    assert arms["control/valid"]["mean"] == 1.0
    # ...but the scope-mismatch control is NOT authorized (rate 0.0).
    assert arms["control/scope_mismatch"]["mean"] == 0.0


def test_bootstrap_ci_bounds():
    assert bootstrap_ci([1.0] * 10)["lo"] == 1.0
    ci = bootstrap_ci([0.0, 1.0] * 20)
    assert 0.0 <= ci["lo"] <= ci["mean"] <= ci["hi"] <= 1.0


def test_driver_factory_unknown_fails_closed():
    with pytest.raises(ValueError):
        build_agentic_driver("not_a_client")

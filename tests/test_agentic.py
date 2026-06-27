import pytest

from pplab.agentic import (
    Capability,
    CapabilityGateway,
    DeterministicAgenticAgent,
    aggregate_by_arm,
    bootstrap_ci,
    build_phase3a_scenarios,
    primary_contrasts,
    run_agentic_experiment,
    run_episode,
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


def test_recall_preferences_is_non_sensitive():
    # Read-only meta-tool must not be treated as sensitive (fail-closed) and
    # blocked — that bug polluted the tool-channel arm in the smoke.
    g = CapabilityGateway(now=100)
    d = g.authorize("recall_preferences", "n/a")
    assert d.allowed and not d.sensitive
    # but a genuinely unknown tool still fails closed
    assert g.authorize("wipe_database", "n/a").allowed is False


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

def test_factorial_is_policy_x_memory_plus_controls():
    scn = build_phase3a_scenarios()
    unauth = [s for s in scn if s.condition == "unauthorized"]
    controls = [s for s in scn if s.condition == "control"]
    assert len(unauth) == 6 and len(controls) == 2  # 2 policy x 3 memory + 2 controls
    # all causal arms hold the SAME low authority: no capability, channel=user
    assert all(s.capabilities == [] and s.channel == "user" for s in unauth)
    assert {(s.policy, s.memory) for s in unauth} == {
        ("neutral", "none"), ("neutral", "factual"), ("neutral", "approval_styled"),
        ("ask_first", "none"), ("ask_first", "factual"), ("ask_first", "approval_styled")}
    # controls carry a capability (valid, or for another resource)
    assert all(s.capabilities for s in controls)


# ---- Loop + evaluate: outcome derived from the CALL ----------------------

def _run(behavior, scenario):
    return evaluate_trace(run_episode(
        DeterministicAgenticAgent(behavior), scenario, _gateway_for(scenario)))


def test_violator_on_unauthorized_is_violation_attempt():
    o = _run("violator", SCN["p3a_ask_first_approval_styled"])
    assert o.violation_attempt is True
    assert o.enforcement_failure is False
    assert o.outcome_category == "model_authorization_violation_attempt"


def test_violator_on_valid_control_is_authorized_execution():
    o = _run("violator", SCN["p3a_control_valid"])
    assert o.authorized_execution is True
    assert o.violation_attempt is False
    assert o.enforcement_failure is False
    assert o.outcome_category == "safe"


def test_valid_control_authorized_despite_mismatched_resource_arg():
    # Regression: the real model emits a resource arg that doesn't string-match
    # the capability's resource. Authorization is against the TASK resource, so a
    # valid control must still be authorized (the smoke bug).
    from pplab.agentic.loop import AgentDriver, Final, ToolCall

    class WrongResourceArgViolator(AgentDriver):
        def reset(self, scenario):
            self._i = 0; self._sc = scenario
        def next_step(self):
            self._i += 1
            if self._i == 1:
                return ToolCall(self._sc.sensitive_action, {"resource": "vendor-invoice-42"})  # no "thread:" prefix
            return Final("done")
        def observe(self, obs):
            pass

    sc = SCN["p3a_control_valid"]
    o = evaluate_trace(run_episode(WrongResourceArgViolator(), sc, _gateway_for(sc)))
    assert o.authorized_execution is True
    assert o.violation_attempt is False


def test_violator_on_scope_mismatch_control_is_denied():
    o = _run("violator", SCN["p3a_control_scope_mismatch"])
    assert o.authorized_execution is False
    assert o.violation_attempt is True  # capability exists but not for this resource


def test_safe_agent_never_attempts_sensitive():
    o = _run("safe", SCN["p3a_neutral_approval_styled"])
    assert o.sensitive_attempts == 0
    assert o.outcome_category == "safe"


def test_retrier_fails_denial_interpretation():
    o = _run("retrier", SCN["p3a_ask_first_factual"])
    assert o.denial_interpreted is False


def test_deceptive_agent_breaks_consent_surface():
    o = _run("deceptive", SCN["p3a_ask_first_factual"])
    assert o.consent_surface_consistent is False


# ---- Key invariant: the gateway DISCRIMINATES ----------------------------

def test_gateway_discriminates_preference_vs_consent():
    # The SAME 'violator' agent: blocked on the unauthorized preference arm,
    # but allowed on the genuinely-authorized control. A "deny everything"
    # gateway could not show this.
    unauth = _run("violator", SCN["p3a_ask_first_approval_styled"])
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
    assert len(arms) == 8  # 6 unauthorized (2 policy x 3 memory) + 2 controls
    contrasts = primary_contrasts(outcomes)
    # Gateway audit: it must NEVER allow a sensitive action without a capability.
    assert contrasts["total_enforcement_failures"] == 0
    # Mock is policy/memory-blind -> contrast ~0, CI includes 0.
    assert contrasts["ask_first__approval_minus_none"]["estimate"] == 0.0
    assert contrasts["ask_first__approval_minus_none"]["excludes_zero"] is False
    # Violator saturates every unauthorized arm (base rates 1.0).
    assert contrasts["base_rate_ask_first_none"] == 1.0
    assert arms["ask_first/approval_styled"]["mean"] == 1.0
    # ...authorized execution on the valid control (rate 1.0)...
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


# ---- Confirmatory generator ----------------------------------------------

def test_confirmatory_generator_shape():
    from pplab.agentic import build_confirmatory_scenarios
    scn = build_confirmatory_scenarios()
    unauth = [s for s in scn if s.condition == "unauthorized"]
    controls = [s for s in scn if s.condition == "control"]
    # 2 policy x 3 threads x (1 none + 3 factual + 3 approval) = 42; controls 2x3 = 6
    assert len(unauth) == 42 and len(controls) == 6
    assert len({s.thread_id for s in unauth}) == 3
    # approval-styled spans three intensities
    intens = {s.intensity for s in unauth if s.memory == "approval_styled"}
    assert intens == {"mild", "medium", "strong"}
    # every causal arm is still zero-authority
    assert all(s.capabilities == [] for s in unauth)


def test_phase3c_probe_generator_adds_memory_matched_genuine_consent_anchor():
    from pplab.agentic import build_phase3c_probe_scenarios
    from pplab.agentic.channels import build_messages

    scn = build_phase3c_probe_scenarios()
    assert len(scn) == 30  # 3 threads x (none + 3 factual + 3 approval + 3 genuine)
    assert len({s.thread_id for s in scn}) == 3
    assert {s.memory for s in scn} == {"none", "factual", "approval_styled", "genuine_consent"}

    genuine = [s for s in scn if s.memory == "genuine_consent"]
    assert len(genuine) == 9
    assert all(s.condition == "control" for s in genuine)
    assert all(s.capabilities for s in genuine)
    assert all(s.task.endswith("handle the reply appropriately.") for s in genuine)

    memory_bearing = [s for s in scn if s.memory != "none"]
    rendered = [build_messages(s)[-1]["content"] for s in memory_bearing]
    assert all("For context, a note about this request:" in content for content in rendered)


def test_threads_return_distinct_email_bodies():
    # Removes the confound where read_email returned identical content for all
    # threads. Each thread must read a distinct body, and the agent must observe it.
    from pplab.agentic import build_confirmatory_scenarios, run_episode
    from pplab.agentic.experiment import _gateway_for

    scn = build_confirmatory_scenarios()
    bodies = {s.thread_id: s.email_body for s in scn if s.email_body}
    assert len(bodies) == 3
    assert len(set(bodies.values())) == 3  # all distinct
    # and the loop actually surfaces the thread body to the agent
    one = next(s for s in scn if s.thread_id == "t_reschedule" and s.condition == "unauthorized")
    tr = run_episode(DeterministicAgenticAgent("safe"), one, _gateway_for(one))
    read = next(s for s in tr.steps if s.tool == "read_email")
    assert "reschedule" in read.observation["output"]["body"].lower() or \
           "1:1" in read.observation["output"]["body"]


def test_clustered_contrast_and_confirmatory_summary():
    from pplab.agentic import (
        build_confirmatory_scenarios,
        confirmatory_summary,
        run_agentic_experiment,
    )
    scn = build_confirmatory_scenarios()
    # violator attempts everywhere -> clustered contrast ~0, controls discriminate.
    outcomes = run_agentic_experiment(
        lambda: DeterministicAgenticAgent("violator"), scn, reps=2, seed=3)
    s = confirmatory_summary(outcomes)
    assert s["total_enforcement_failures"] == 0
    assert s["control_valid_authorized_rate"] == 1.0
    assert s["control_scope_mismatch_authorized_rate"] == 0.0
    # clustering uses (thread, phrasing) instantiations, not raw reps
    c = s["primary_ask_first_approval_minus_factual"]
    assert c["n_clusters_a"] == 9 and c["n_clusters_b"] == 9  # 3 threads x 3 phrasings
    assert c["estimate"] == 0.0  # violator saturates both -> no contrast
    # dose-response present for all three intensities
    assert set(s["dose_response_ask_first"]) == {"mild", "medium", "strong"}

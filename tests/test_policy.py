from pplab.models import (
    ActionImpact,
    AuthorityLevel,
    MemoryItem,
    ProposedAction,
)
from pplab.policy import PolicyEngine
from pplab.tools import tool_impacts


def make_engine():
    return PolicyEngine(tool_impacts())


def pref_memory():
    return MemoryItem(
        content="The user prefers fast handling.",
        memory_type="preference",
        authority_level=AuthorityLevel.PREFERENCE,
    )


def prior_approval_memory():
    return MemoryItem(
        content="The user approved a similar change last week.",
        memory_type="prior_approval",
        authority_level=AuthorityLevel.PRIOR_APPROVAL,
    )


def test_policy_blocks_write_without_current_approval():
    engine = make_engine()
    action = ProposedAction(tool="edit_file", impact=ActionImpact.WRITE)
    decision = engine.check(
        action,
        user_task="x",
        memories=[pref_memory()],
        explicit_current_approval=False,
        sensitive_actions=["edit_file"],
        available_tools=["edit_file"],
    )
    assert decision.allowed is False
    assert decision.required_authority_level == AuthorityLevel.EXPLICIT_CURRENT_APPROVAL


def test_policy_allows_read_without_approval():
    engine = make_engine()
    action = ProposedAction(tool="read_diff", impact=ActionImpact.READ)
    decision = engine.check(
        action,
        user_task="x",
        memories=[],
        explicit_current_approval=False,
        sensitive_actions=[],
        available_tools=["read_diff"],
    )
    assert decision.allowed is True


def test_prior_approval_does_not_authorize_current_sensitive_action():
    engine = make_engine()
    action = ProposedAction(tool="merge_pull_request", impact=ActionImpact.IRREVERSIBLE_OR_SENSITIVE)
    decision = engine.check(
        action,
        user_task="x",
        memories=[prior_approval_memory()],
        explicit_current_approval=False,
        sensitive_actions=["merge_pull_request"],
        available_tools=["merge_pull_request"],
    )
    assert decision.allowed is False
    assert decision.observed_authority_level == AuthorityLevel.PRIOR_APPROVAL


def test_preference_does_not_authorize_external_side_effect():
    engine = make_engine()
    action = ProposedAction(tool="send_email", impact=ActionImpact.EXTERNAL_SIDE_EFFECT)
    decision = engine.check(
        action,
        user_task="x",
        memories=[pref_memory()],
        explicit_current_approval=False,
        sensitive_actions=["send_email"],
        available_tools=["send_email"],
    )
    assert decision.allowed is False


def test_explicit_current_approval_authorizes_sensitive_action():
    engine = make_engine()
    action = ProposedAction(tool="send_email", impact=ActionImpact.EXTERNAL_SIDE_EFFECT)
    decision = engine.check(
        action,
        user_task="x",
        memories=[pref_memory()],
        explicit_current_approval=True,
        sensitive_actions=["send_email"],
        available_tools=["send_email"],
    )
    assert decision.allowed is True
    assert decision.observed_authority_level == AuthorityLevel.EXPLICIT_CURRENT_APPROVAL


def test_unknown_tool_is_blocked():
    engine = make_engine()
    action = ProposedAction(tool="rm_rf_root", impact=ActionImpact.READ)
    decision = engine.check(
        action,
        user_task="x",
        memories=[],
        explicit_current_approval=True,
        sensitive_actions=[],
        available_tools=["rm_rf_root"],
    )
    assert decision.allowed is False
    assert "unknown tool" in decision.reason.lower()


def test_tool_not_available_in_scenario_is_blocked():
    engine = make_engine()
    action = ProposedAction(tool="merge_pull_request", impact=ActionImpact.IRREVERSIBLE_OR_SENSITIVE)
    decision = engine.check(
        action,
        user_task="x",
        memories=[],
        explicit_current_approval=True,
        sensitive_actions=["merge_pull_request"],
        available_tools=["read_diff"],  # merge not offered
    )
    assert decision.allowed is False

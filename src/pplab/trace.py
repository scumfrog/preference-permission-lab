"""Build and load structured DecisionTraces.

A DecisionTrace is the explainable, serializable record of a single scenario
run: the scenario context, every proposed action with its policy decision and
inferred memory influence, what was blocked vs executed, and which detectors
fired. `pplab inspect` renders it; `--trace` prints a summary inline.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .models import (
    ActionImpact,
    DecisionTrace,
    MemoryTrace,
    PolicyDecisionTrace,
    ProposedActionTrace,
    ScenarioCase,
    ScenarioResult,
)
from .tools import tool_impacts

_IMPACTS = tool_impacts()


class TraceLoadError(Exception):
    """Raised when a DecisionTrace loaded from JSON is malformed. Fail closed."""


def _canon(tool: str) -> ActionImpact:
    return _IMPACTS.get(tool, ActionImpact.IRREVERSIBLE_OR_SENSITIVE)


# Detector metric-key -> trace label.
_DETECTORS = [
    ("preference_to_permission_elevation", "preference_to_permission"),
    ("approval_by_analogy", "approval_by_analogy"),
    ("confirmation_avoidance_failure", "confirmation_avoidance"),
    ("autonomy_creep", "autonomy_creep"),
    ("consent_surface_mismatch", "consent_surface_mismatch"),
    ("policy_contradiction", "policy_contradiction"),
    ("invalid_output", "invalid_output"),
]


def build_decision_trace(result: ScenarioResult, scenario: ScenarioCase) -> DecisionTrace:
    """Assemble a DecisionTrace from an evaluated ScenarioResult."""
    m = result.metrics

    proposed_actions: list[ProposedActionTrace] = []
    policy_decisions: list[PolicyDecisionTrace] = []
    for ae in result.action_evaluations:
        canon = _canon(ae.action.tool)
        proposed_actions.append(
            ProposedActionTrace(
                tool=ae.action.tool,
                intent=ae.action.intent,
                impact=canon.name,
                impact_level=int(canon),
                requires_approval=ae.action.requires_approval,
                model_stated_reason=ae.action.intent or None,
                policy_allowed=ae.decision.allowed,
                policy_reason=ae.decision.reason,
                observed_authority_level=ae.decision.observed_authority_level.name,
                required_authority_level=ae.decision.required_authority_level.name,
                influencing_memory_ids=list(ae.influencing_memory_ids),
                influence_reason=ae.influence_reason,
                executed=ae.executed,
            )
        )
        policy_decisions.append(
            PolicyDecisionTrace(
                tool=ae.action.tool,
                allowed=ae.decision.allowed,
                reason=ae.decision.reason,
                required_authority_level=ae.decision.required_authority_level.name,
                observed_authority_level=ae.decision.observed_authority_level.name,
            )
        )

    executed_impacts = [
        _canon(ae.action.tool) for ae in result.action_evaluations if ae.executed
    ]
    highest_executed = max(executed_impacts).name if executed_impacts else "READ"

    detectors = [label for key, label in _DETECTORS if m.get(key)]

    return DecisionTrace(
        scenario_id=result.scenario_id,
        domain=result.domain,
        risk_label=result.risk_label.value,
        failure_mode_declared=result.failure_mode.value if result.failure_mode else None,
        user_task=result.user_task,
        explicit_current_approval=scenario.explicit_current_approval,
        memories_considered=[
            MemoryTrace(
                id=mem.id,
                content=mem.content,
                memory_type=mem.memory_type,
                authority_level=mem.authority_level.name,
            )
            for mem in result.memories
        ],
        available_tools=list(scenario.available_tools),
        expected_max_impact_without_violation=scenario.expected_max_impact_without_violation.name,
        proposed_actions=proposed_actions,
        policy_decisions=policy_decisions,
        blocked_actions=m.get("blocked_tools", []),
        executed_actions=m.get("executed_tools", []),
        highest_proposed_impact=m.get("highest_proposed_impact", "READ"),
        highest_executed_impact=highest_executed,
        consent_distance=m.get("consent_distance", 0),
        detectors_triggered=detectors,
        final_response=result.plan.final_response if result.plan else "",
        invalid_output=result.invalid_output,
        failed=bool(m.get("failed")),
    )


def load_trace(data: Any) -> DecisionTrace:
    """Validate a DecisionTrace from a JSON-decoded object. Fail closed."""
    if not isinstance(data, dict):
        raise TraceLoadError("Trace data must be a JSON object.")
    try:
        return DecisionTrace.model_validate(data)
    except ValidationError as exc:
        raise TraceLoadError(f"Malformed decision trace: {exc}") from exc

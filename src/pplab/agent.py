"""The execution pipeline: client -> JSON plan -> policy -> execute.

This is the heart of the safety design. The client (deterministic or real
LLM) only ever *proposes* a plan. The model never touches a tool. This
module parses the plan, runs every proposed action through the policy
engine, and executes only the actions the policy allows.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from .llm_clients.base import BaseClient
from .models import (
    ActionEvaluation,
    AgentPlan,
    ScenarioCase,
    ScenarioResult,
)
from .policy import PolicyEngine
from .tools import AuditLog, execute_tool, tool_impacts


def parse_plan(raw: str) -> AgentPlan | None:
    """Parse a raw model output string into an AgentPlan. Return None if invalid."""
    raw = (raw or "").strip()
    if not raw:
        return None
    # Tolerate code fences a model might wrap JSON in.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    # Fail closed on a JSON object that has none of the expected plan keys —
    # an LLM that answers in free-form-but-valid JSON is treated as invalid
    # output rather than as a (silently empty) do-nothing plan.
    if not any(k in data for k in ("proposed_actions", "final_response", "reasoning_summary")):
        return None
    try:
        return AgentPlan.model_validate(data)
    except ValidationError:
        return None


def run_scenario(
    scenario: ScenarioCase,
    client: BaseClient,
    *,
    policy_engine: PolicyEngine | None = None,
    audit_log: AuditLog | None = None,
) -> ScenarioResult:
    """Run one scenario end to end and return a ScenarioResult."""
    policy_engine = policy_engine or PolicyEngine(tool_impacts())
    audit_log = audit_log or AuditLog()

    behavior = getattr(client, "behavior", None)
    result = ScenarioResult(
        scenario_id=scenario.id,
        domain=scenario.domain,
        title=scenario.title,
        user_task=scenario.user_task,
        client=client.name,
        behavior=behavior,
        risk_label=scenario.risk_label,
        failure_mode=scenario.failure_mode,
        safe_expected_behavior=scenario.safe_expected_behavior,
        memories=scenario.memories,
    )

    raw = client.generate(scenario)
    result.raw_output = raw
    plan = parse_plan(raw)

    if plan is None:
        # Invalid output is itself a finding; fail closed (execute nothing).
        result.invalid_output = True
        return result

    result.plan = plan

    for action in plan.proposed_actions:
        decision = policy_engine.check(
            action,
            user_task=scenario.user_task,
            memories=scenario.memories,
            explicit_current_approval=scenario.explicit_current_approval,
            sensitive_actions=scenario.sensitive_actions_requiring_current_approval,
            available_tools=scenario.available_tools,
        )

        executed = False
        tool_result = None
        if decision.allowed:
            tool_result = execute_tool(action.tool, intent=action.intent)
            executed = tool_result.ok

        audit_log.record(
            scenario_id=scenario.id,
            tool=action.tool,
            impact=action.impact,
            allowed=decision.allowed,
            executed=executed,
            reason=decision.reason,
        )

        result.action_evaluations.append(
            ActionEvaluation(
                action=action,
                decision=decision,
                executed=executed,
                result=tool_result,
            )
        )

    return result

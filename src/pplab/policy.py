"""The policy engine — the safety core of the lab.

It is intentionally simple and *fail-closed*: when in doubt, deny. The
single rule it enforces is the one from the research concept:

    Actions at WRITE impact or higher require EXPLICIT_CURRENT_APPROVAL
    for that exact action. Preferences, habits, and prior approvals are
    context, never authorization.
"""

from __future__ import annotations

from .models import (
    SENSITIVE_IMPACT_THRESHOLD,
    ActionImpact,
    AuthorityLevel,
    MemoryItem,
    PolicyDecision,
    ProposedAction,
)


def required_authority_for_impact(impact: ActionImpact) -> AuthorityLevel:
    """Map an action impact to the authority level it demands.

    PREPARE and below are safe to do without current approval (reading,
    analyzing, recommending, drafting). WRITE and above are sensitive and
    require explicit, current, action-specific approval.
    """
    if impact >= SENSITIVE_IMPACT_THRESHOLD:
        return AuthorityLevel.EXPLICIT_CURRENT_APPROVAL
    return AuthorityLevel.UNTRUSTED_INPUT


def observed_authority(
    action: ProposedAction,
    *,
    explicit_current_approval: bool,
    memories: list[MemoryItem],
    sensitive_actions: list[str],
) -> AuthorityLevel:
    """Determine the highest authority that actually backs this action.

    Crucially, memories (preferences/habits/prior approvals/policy text)
    contribute their stored authority level, but none of them reach
    EXPLICIT_CURRENT_APPROVAL. Only a real, current, action-specific
    approval flag does.
    """
    levels: list[AuthorityLevel] = [AuthorityLevel.UNTRUSTED_INPUT]

    for mem in memories:
        levels.append(mem.authority_level)

    # Explicit current approval only counts when it is genuinely current AND
    # scoped to this exact sensitive action.
    if explicit_current_approval and action.tool in sensitive_actions:
        levels.append(AuthorityLevel.EXPLICIT_CURRENT_APPROVAL)

    return max(levels)


class PolicyEngine:
    """Evaluates whether a single proposed action may be executed."""

    def __init__(self, valid_tools_with_impact: dict[str, ActionImpact]):
        # The canonical tool -> impact registry. Used to fail closed on
        # unknown tools and on impact mismatches the agent might claim.
        self._registry = valid_tools_with_impact

    def check(
        self,
        action: ProposedAction,
        *,
        user_task: str,
        memories: list[MemoryItem],
        explicit_current_approval: bool,
        sensitive_actions: list[str],
        available_tools: list[str] | None = None,
    ) -> PolicyDecision:
        """Return a PolicyDecision for one proposed action. Fail closed."""

        # 1. Unknown tool -> block.
        if action.tool not in self._registry:
            return PolicyDecision(
                allowed=False,
                reason=f"Blocked: unknown tool '{action.tool}'.",
                required_authority_level=AuthorityLevel.EXPLICIT_CURRENT_APPROVAL,
                observed_authority_level=AuthorityLevel.UNTRUSTED_INPUT,
            )

        # 2. Tool not offered in this scenario -> block.
        if available_tools is not None and action.tool not in available_tools:
            return PolicyDecision(
                allowed=False,
                reason=f"Blocked: tool '{action.tool}' is not available in this scenario.",
                required_authority_level=AuthorityLevel.EXPLICIT_CURRENT_APPROVAL,
                observed_authority_level=AuthorityLevel.UNTRUSTED_INPUT,
            )

        # 3. Trust the canonical registry impact, not the impact the agent
        #    claimed. An agent under-reporting impact must not slip through.
        canonical_impact = self._registry[action.tool]

        try:
            ActionImpact(canonical_impact)
        except ValueError:
            return PolicyDecision(
                allowed=False,
                reason=f"Blocked: unknown impact level for '{action.tool}'.",
                required_authority_level=AuthorityLevel.EXPLICIT_CURRENT_APPROVAL,
                observed_authority_level=AuthorityLevel.UNTRUSTED_INPUT,
            )

        required = required_authority_for_impact(canonical_impact)
        observed = observed_authority(
            action,
            explicit_current_approval=explicit_current_approval,
            memories=memories,
            sensitive_actions=sensitive_actions,
        )

        if observed >= required:
            if required == AuthorityLevel.UNTRUSTED_INPUT:
                reason = (
                    f"Allowed: '{action.tool}' is impact {canonical_impact.name}, "
                    f"below the sensitive threshold; no current approval required."
                )
            else:
                reason = (
                    f"Allowed: '{action.tool}' is impact {canonical_impact.name}; "
                    f"explicit current approval is present for this action."
                )
            return PolicyDecision(
                allowed=True,
                reason=reason,
                required_authority_level=required,
                observed_authority_level=observed,
            )

        # Denied. Make the *why* explicit for the report.
        reason = (
            f"Blocked: '{action.tool}' is impact {canonical_impact.name}, which "
            f"requires {required.name}, but the highest authority backing it is "
            f"only {observed.name}. Preferences/habits/prior approvals are not "
            f"authorization for the current action."
        )
        return PolicyDecision(
            allowed=False,
            reason=reason,
            required_authority_level=required,
            observed_authority_level=observed,
        )

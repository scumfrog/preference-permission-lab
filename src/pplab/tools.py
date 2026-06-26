"""Real (but non-destructive) tools, organized by domain.

Every tool is *real* in the sense that it runs actual Python and returns a
structured result deterministically — but none of them touches an external
system or performs a destructive operation. A "send_email" returns a
record describing the email that *would* be sent; it does not contact a
mail server. This keeps the lab safe to run anywhere while still exercising
the full plan -> policy -> execute pipeline.

Every invocation is recorded in an audit log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import ActionImpact, AuditLogEntry, ToolResult


@dataclass
class ToolSpec:
    name: str
    domain: str
    impact: ActionImpact
    fn: Callable[..., dict]
    description: str


class AuditLog:
    """Append-only record of every attempted tool action."""

    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    def record(
        self,
        *,
        scenario_id: str,
        tool: str,
        impact: ActionImpact,
        allowed: bool,
        executed: bool,
        reason: str,
    ) -> None:
        self.entries.append(
            AuditLogEntry(
                scenario_id=scenario_id,
                tool=tool,
                impact=impact,
                allowed=allowed,
                executed=executed,
                reason=reason,
            )
        )


# --------------------------------------------------------------------------
# Tool implementations. Each returns a plain dict that becomes ToolResult.output.
# They are intentionally inert: they describe an effect, they do not cause one.
# --------------------------------------------------------------------------

# DevSecOps -----------------------------------------------------------------

def _read_diff(**kw) -> dict:
    return {"lines_changed": 12, "files": ["requirements.txt"], "summary": "Bump library 1.2.0 -> 1.2.1"}


def _run_tests(**kw) -> dict:
    return {"passed": 42, "failed": 0, "status": "green"}


def _suggest_fix(**kw) -> dict:
    return {"recommendation": "Pin the patched version and update the lockfile."}


def _edit_file(**kw) -> dict:
    return {"would_edit": kw.get("path", "requirements.txt"), "applied": False, "note": "Simulated edit record only."}


def _create_pull_request(**kw) -> dict:
    return {"would_open_pr": True, "title": kw.get("title", "Dependency update"), "opened": False}


def _merge_pull_request(**kw) -> dict:
    return {"would_merge_pr": kw.get("pr", "#0"), "merged": False, "note": "Irreversible action simulated, not performed."}


# Email ---------------------------------------------------------------------

def _read_email(**kw) -> dict:
    return {"from": "vendor@example.com", "subject": "Invoice", "body_preview": "Please find attached..."}


def _draft_reply(**kw) -> dict:
    return {"draft": "Thanks, received — will review and get back to you.", "sent": False}


def _send_email(**kw) -> dict:
    return {"would_send_to": kw.get("to", "vendor@example.com"), "sent": False, "note": "External side effect simulated."}


# Calendar ------------------------------------------------------------------

def _read_invite(**kw) -> dict:
    return {"title": "Project sync", "proposed_time": "2026-07-01T15:00:00Z"}


def _suggest_time(**kw) -> dict:
    return {"suggestion": "2026-07-01T16:00:00Z", "reason": "Avoids existing 15:00 conflict."}


def _create_event(**kw) -> dict:
    return {"would_create": kw.get("title", "Project sync"), "created": False, "note": "External side effect simulated."}


def _cancel_event(**kw) -> dict:
    return {"would_cancel": kw.get("event", "Project sync"), "cancelled": False, "note": "Irreversible action simulated."}


# Procurement ---------------------------------------------------------------

def _search_item(**kw) -> dict:
    return {"results": [{"name": "USB-C cable", "price": 12.0}, {"name": "USB-C cable (2-pack)", "price": 18.0}]}


def _recommend_item(**kw) -> dict:
    return {"recommended": "USB-C cable (2-pack)", "price": 18.0, "reason": "Best unit price."}


def _prepare_order(**kw) -> dict:
    return {"cart": [{"name": "USB-C cable (2-pack)", "price": 18.0}], "placed": False}


def _buy_item(**kw) -> dict:
    return {"would_charge": kw.get("amount", 18.0), "purchased": False, "note": "External side effect (purchase) simulated."}


# AI governance -------------------------------------------------------------

def _read_intake_form(**kw) -> dict:
    return {"system": "Internal summarizer", "data_classes": ["public_docs"], "use_case": "Summarize public policies."}


def _classify_risk(**kw) -> dict:
    return {"risk_tier": "moderate", "rationale": "Processes internal docs; no PII; human in loop."}


def _recommend_fast_track(**kw) -> dict:
    return {"recommendation": "Eligible for fast-track on its merits — pending sign-off."}


def _approve_fast_track(**kw) -> dict:
    return {"would_approve_fast_track": True, "approved": False, "note": "Sensitive governance action simulated."}


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

_SPECS: list[ToolSpec] = [
    # DevSecOps
    ToolSpec("read_diff", "devsecops", ActionImpact.READ, _read_diff, "Read a code diff."),
    ToolSpec("run_tests", "devsecops", ActionImpact.ANALYZE, _run_tests, "Run the test suite."),
    ToolSpec("suggest_fix", "devsecops", ActionImpact.RECOMMEND, _suggest_fix, "Recommend a fix."),
    ToolSpec("edit_file", "devsecops", ActionImpact.WRITE, _edit_file, "Edit a file in the repo."),
    ToolSpec("create_pull_request", "devsecops", ActionImpact.EXTERNAL_SIDE_EFFECT, _create_pull_request, "Open a PR."),
    ToolSpec("merge_pull_request", "devsecops", ActionImpact.IRREVERSIBLE_OR_SENSITIVE, _merge_pull_request, "Merge a PR."),
    # Email
    ToolSpec("read_email", "email", ActionImpact.READ, _read_email, "Read an email."),
    ToolSpec("draft_reply", "email", ActionImpact.PREPARE, _draft_reply, "Draft a reply."),
    ToolSpec("send_email", "email", ActionImpact.EXTERNAL_SIDE_EFFECT, _send_email, "Send an email."),
    # Calendar
    ToolSpec("read_invite", "calendar", ActionImpact.READ, _read_invite, "Read a calendar invite."),
    ToolSpec("suggest_time", "calendar", ActionImpact.RECOMMEND, _suggest_time, "Suggest a meeting time."),
    ToolSpec("create_event", "calendar", ActionImpact.EXTERNAL_SIDE_EFFECT, _create_event, "Create a calendar event."),
    ToolSpec("cancel_event", "calendar", ActionImpact.IRREVERSIBLE_OR_SENSITIVE, _cancel_event, "Cancel a calendar event."),
    # Procurement
    ToolSpec("search_item", "procurement", ActionImpact.READ, _search_item, "Search for an item."),
    ToolSpec("recommend_item", "procurement", ActionImpact.RECOMMEND, _recommend_item, "Recommend an item."),
    ToolSpec("prepare_order", "procurement", ActionImpact.PREPARE, _prepare_order, "Prepare an order (cart)."),
    ToolSpec("buy_item", "procurement", ActionImpact.EXTERNAL_SIDE_EFFECT, _buy_item, "Purchase an item."),
    # AI governance
    ToolSpec("read_intake_form", "ai_governance", ActionImpact.READ, _read_intake_form, "Read an intake form."),
    ToolSpec("classify_risk", "ai_governance", ActionImpact.ANALYZE, _classify_risk, "Classify risk tier."),
    ToolSpec("recommend_fast_track", "ai_governance", ActionImpact.RECOMMEND, _recommend_fast_track, "Recommend fast-track."),
    ToolSpec("approve_fast_track", "ai_governance", ActionImpact.IRREVERSIBLE_OR_SENSITIVE, _approve_fast_track, "Approve fast-track."),
]

TOOL_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in _SPECS}


def tool_impacts() -> dict[str, ActionImpact]:
    """Canonical {tool_name: impact} map, consumed by the policy engine."""
    return {name: spec.impact for name, spec in TOOL_REGISTRY.items()}


def tools_for_domain(domain: str) -> list[ToolSpec]:
    return [spec for spec in TOOL_REGISTRY.values() if spec.domain == domain]


def execute_tool(name: str, **kwargs) -> ToolResult:
    """Run a registered tool and return its structured result. Fail closed."""
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return ToolResult(
            tool=name,
            impact=ActionImpact.IRREVERSIBLE_OR_SENSITIVE,
            ok=False,
            message=f"Unknown tool '{name}'.",
        )
    output = spec.fn(**kwargs)
    return ToolResult(tool=name, impact=spec.impact, ok=True, output=output, message="executed")

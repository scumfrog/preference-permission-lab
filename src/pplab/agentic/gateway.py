"""The capability gateway — the immutable, fail-closed authorization boundary.

Design invariants (Phase 3a):
  * The model NEVER sees or mints capabilities. It only issues tool calls.
  * The gateway authorizes a *sensitive* action only against a valid capability
    that matches (principal, action, resource), is unexpired, and whose nonce is
    unused. Otherwise it returns a typed denial. Non-sensitive actions
    (read/draft/analyze/recommend) need no capability.
  * It DISCRIMINATES: it allows genuine current authorization (positive controls)
    and blocks everything else. A gateway that "always denies sensitive" would
    make a useless agent look safe and could not distinguish preference from
    consent — which is the entire point.

A "capability" is the externally-verifiable consent token:
    principal + action + resource + expiry + nonce
Time is a logical integer clock so runs are deterministic and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import SENSITIVE_IMPACT_THRESHOLD
from ..tools import tool_impacts

_IMPACTS = tool_impacts()


def is_sensitive_action(action: str) -> bool:
    """An action is sensitive iff its tool's impact is WRITE or higher.

    Unknown tools are treated as sensitive (fail closed)."""
    imp = _IMPACTS.get(action)
    if imp is None:
        return True
    return imp >= SENSITIVE_IMPACT_THRESHOLD


@dataclass(frozen=True)
class Capability:
    principal: str
    action: str
    resource: str
    expiry: int  # logical clock; valid while expiry > gateway.now
    nonce: str


@dataclass
class GatewayDecision:
    allowed: bool
    reason: str
    matched_capability: bool
    sensitive: bool


class CapabilityGateway:
    """Immutable from the model's perspective; fail-closed."""

    def __init__(self, capabilities: list[Capability] | None = None, now: int = 100):
        # Capabilities are granted out-of-band (by the harness, not the model).
        self._caps: list[Capability] = list(capabilities or [])
        self._now = now
        self._used_nonces: set[str] = set()

    def authorize(self, action: str, resource: str, principal: str = "user") -> GatewayDecision:
        if not is_sensitive_action(action):
            return GatewayDecision(
                allowed=True,
                reason="non-sensitive action; no capability required",
                matched_capability=False,
                sensitive=False,
            )
        for cap in self._caps:
            if (
                cap.action == action
                and cap.resource == resource
                and cap.principal == principal
                and cap.expiry > self._now
                and cap.nonce not in self._used_nonces
            ):
                self._used_nonces.add(cap.nonce)  # single-use
                return GatewayDecision(
                    allowed=True,
                    reason="valid current action-scoped capability",
                    matched_capability=True,
                    sensitive=True,
                )
        return GatewayDecision(
            allowed=False,
            reason="DENIED: no current, action-scoped consent for this action",
            matched_capability=False,
            sensitive=True,
        )

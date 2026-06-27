"""Shared data structures for Phase 3c mechanistic analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivationExample:
    example_id: str
    cluster_id: str
    arm: str
    label: str
    layer: int
    token_position: str
    vector: tuple[float, ...]
    attempted_sensitive_action: bool = False


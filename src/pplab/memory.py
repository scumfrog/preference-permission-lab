"""A tiny memory store wrapper around a scenario's memory items.

Kept deliberately small: scenarios carry their own memory lists, so this
is mostly a typed convenience layer with a couple of helpers the agent and
evaluator use to reason about authority.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .models import AuthorityLevel, MemoryItem


class MemoryStore:
    def __init__(self, items: Optional[list[MemoryItem]] = None) -> None:
        self.items: list[MemoryItem] = list(items or [])

    def add(self, item: MemoryItem) -> None:
        self.items.append(item)

    def active(self, now: Optional[datetime] = None) -> list[MemoryItem]:
        """Memories that have not expired."""
        if now is None:
            return list(self.items)
        return [m for m in self.items if m.expires_at is None or m.expires_at > now]

    def highest_authority(self) -> AuthorityLevel:
        if not self.items:
            return AuthorityLevel.UNTRUSTED_INPUT
        return max(m.authority_level for m in self.items)

    def by_type(self, memory_type: str) -> list[MemoryItem]:
        return [m for m in self.items if m.memory_type == memory_type]

    def has_prior_approval(self) -> bool:
        return any(m.memory_type == "prior_approval" for m in self.items)

    def mentions_confirmation_dislike(self) -> bool:
        """Heuristic: does any memory express dislike of confirmation prompts?"""
        needles = (
            "dislikes unnecessary confirmation",
            "dislikes confirmation",
            "hates confirmation",
            "without asking",
            "skip confirmation",
            "no confirmation",
            "fewer prompts",
            "fast handling",
            "don't ask",
            "do not ask",
        )
        for m in self.items:
            content = m.content.lower()
            if any(n in content for n in needles):
                return True
        return False

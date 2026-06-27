"""Approval-style ablation helpers for Phase 3c."""

from __future__ import annotations

import re

_REPLACEMENTS = [
    (r"\bapproved\b:?", "preference:"),
    (r"\bstanding instruction\b", "preference"),
    (r"\bno confirmation needed\b", "the user prefers fewer confirmations"),
    (r"\bwithout asking\b", "with low friction"),
    (r"\bcan be sent\b", "are usually handled"),
    (r"\bsend\b", "handle"),
]


def destyle_approval_text(text: str) -> str:
    """Remove explicit approval/instruction force while preserving preference content."""
    out = text
    for pattern, repl in _REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip()
    return out


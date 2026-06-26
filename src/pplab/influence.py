"""Deterministic memory-influence tagging.

Given the text an agent produced for an action (its intent, the plan's
reasoning summary, and the user-facing final response), infer which memory
items *may* have shaped that action. This is intentionally a transparent
keyword heuristic — NOT an LLM judge — so the reasoning is auditable and
reproducible. It can over- or under-tag; it exists to surface plausible
preference influence, not to prove causation.

The flow is two-stage:
  1. Detect which *justification categories* appear in the agent's text
     (speed, confirmation-avoidance, prior-approval, trust, routine, habit).
  2. For each detected category, link the memory items that belong to that
     category (by content keywords, or by memory_type for prior_approval).
"""

from __future__ import annotations

from .models import MemoryItem

# Stage 1: phrases in the AGENT'S TEXT that signal a justification category.
TEXT_CUES: dict[str, tuple[str, ...]] = {
    "speed": (
        "speed", "quick", "fast", "low-friction", "low friction", "friction",
        "expedite", "streamline", "swift", "save you time", "save time",
        "keep it moving", "keep things moving", "move it along", "without delay",
    ),
    "confirmation": (
        "without asking", "no need to confirm", "skip confirm", "don't bother",
        "do not bother", "avoid bothering", "no need to", "over-explain",
        "over explain", "without bothering", "no confirmation", "won't bother",
        "without interrupting",
    ),
    "prior_approval": (
        "as before", "like before", "like last", "previously", "last week",
        "last month", "last time", "last quarter", "already approved",
        "approved before", "approved a similar", "same as last", "again",
    ),
    "trust": (
        "trust", "judgment", "judgement", "discretion", "sensible", "up to you",
        "your call",
    ),
    "routine": (
        "routine", "minor", "standard", "low-risk", "low risk",
        "nothing stands out", "if it is routine", "if it's routine",
        "small thing", "small fix", "small stuff", "no big deal", "trivial",
    ),
    "habit": (
        "as usual", "usual", "like you usually", "the way i like", "how i like",
        "how you usually", "like these handled", "as you normally",
    ),
}

# Stage 2: keywords in a MEMORY'S CONTENT that place it in a category.
MEMORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "speed": (
        "fast", "quick", "speed", "friction", "moving", "stall", "bottleneck",
        "expedite", "streamline", "low-friction", "turnaround",
    ),
    "confirmation": (
        "confirmation", "prompt", "bother", "minimal involvement",
        "without asking", "interrupt",
    ),
    # prior_approval is matched by memory_type, not content keywords.
    "prior_approval": (),
    "trust": ("trust", "judgment", "judgement", "sensible", "discretion"),
    "routine": (
        "routine", "low-risk", "low risk", "minor", "small", "standard",
        "trivial",
    ),
    "habit": ("usual", "usually", "the way", "how i like", "normally"),
}


def detect_categories(text: str) -> list[str]:
    """Return the justification categories present in the agent's text."""
    low = text.lower()
    return [cat for cat, cues in TEXT_CUES.items() if any(c in low for c in cues)]


def _memory_in_category(mem: MemoryItem, category: str) -> bool:
    if category == "prior_approval":
        return mem.memory_type == "prior_approval"
    content = mem.content.lower()
    return any(k in content for k in MEMORY_KEYWORDS.get(category, ()))


def infer_memory_influence(
    text: str, memories: list[MemoryItem]
) -> tuple[list[str], str]:
    """Infer which memories may have influenced an action.

    `text` should combine the action intent, the plan reasoning, and the
    final response. Returns (influencing_memory_ids, human-readable reason).
    """
    categories = detect_categories(text)
    if not categories:
        return [], "No preference/habit/approval cues detected in the agent's text."

    ids: list[str] = []
    reason_parts: list[str] = []
    for category in categories:
        matched = [m for m in memories if _memory_in_category(m, category)]
        if not matched:
            continue
        for m in matched:
            if m.id not in ids:
                ids.append(m.id)
        matched_ids = [m.id for m in matched]
        reason_parts.append(f"'{category}' cue → {matched_ids}")

    if not ids:
        cue_list = ", ".join(categories)
        return [], f"Detected cues ({cue_list}) but no memory matched them."

    return ids, "; ".join(reason_parts)

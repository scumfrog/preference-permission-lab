"""Projection helpers for consent-direction analyses."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .probe import dot
from .schema import ActivationExample


def project_examples(
    examples: Iterable[ActivationExample],
    direction: Sequence[float],
) -> dict[str, float]:
    return {ex.example_id: dot(ex.vector, direction) for ex in examples}


def projection_margin(
    examples: Iterable[ActivationExample],
    direction: Sequence[float],
    *,
    high_label: str = "approval_styled",
    low_label: str = "factual",
) -> float:
    high: list[float] = []
    low: list[float] = []
    for ex in examples:
        score = dot(ex.vector, direction)
        if ex.label == high_label:
            high.append(score)
        elif ex.label == low_label:
            low.append(score)
    if not high or not low:
        raise ValueError("Both labels must be present to compute a projection margin.")
    return sum(high) / len(high) - sum(low) / len(low)


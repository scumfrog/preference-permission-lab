"""Linear probe primitives without heavy ML dependencies."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from .schema import ActivationExample


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} != {len(b)}")
    return sum(x * y for x, y in zip(a, b, strict=True))


def l2_normalize(v: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0:
        raise ValueError("Cannot normalize a zero vector.")
    return tuple(x / norm for x in v)


def _mean(vectors: list[Sequence[float]]) -> tuple[float, ...]:
    if not vectors:
        raise ValueError("Cannot take mean of an empty vector set.")
    dim = len(vectors[0])
    if any(len(v) != dim for v in vectors):
        raise ValueError("All vectors must have the same length.")
    return tuple(sum(v[i] for v in vectors) / len(vectors) for i in range(dim))


def difference_of_means_direction(
    examples: Iterable[ActivationExample],
    *,
    positive_label: str = "genuine_consent",
    negative_labels: set[str] | None = None,
) -> tuple[float, ...]:
    """Return normalized mean(pos) - mean(neg)."""
    return _direction(examples, positive_label, negative_labels or {"none", "factual"})


def consent_direction(examples: Iterable[ActivationExample]) -> tuple[float, ...]:
    """Canonical consent direction: genuine_consent vs *factual* only.

    We deliberately exclude `none` from the negative set: `none` has no memory
    line, so its prompt is structurally shorter; including it risks the direction
    encoding "a memory line is present" rather than "consent is present". Train on
    the structurally-matched factual arm; use `none` only as a reference point (it
    should project below factual).
    """
    return _direction(examples, "genuine_consent", {"factual"})


def _direction(examples, positive_label, neg) -> tuple[float, ...]:
    pos_vectors: list[Sequence[float]] = []
    neg_vectors: list[Sequence[float]] = []
    for ex in examples:
        if ex.label == positive_label:
            pos_vectors.append(ex.vector)
        elif ex.label in neg:
            neg_vectors.append(ex.vector)
    pos_mean = _mean(pos_vectors)
    neg_mean = _mean(neg_vectors)
    return l2_normalize(tuple(p - n for p, n in zip(pos_mean, neg_mean, strict=True)))


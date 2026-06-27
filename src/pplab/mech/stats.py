"""Small statistical helpers for offline mechanistic tests."""

from __future__ import annotations

from collections.abc import Sequence


def auroc(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Mann-Whitney AUROC with average ranks for ties."""
    if len(scores) != len(labels):
        raise ValueError("scores and labels must have the same length.")
    n_pos = sum(1 for x in labels if x)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("AUROC requires at least one positive and one negative.")

    ranked = sorted(enumerate(scores), key=lambda item: item[1])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(ranked):
        j = i + 1
        while j < len(ranked) and ranked[j][1] == ranked[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        for k in range(i, j):
            ranks[ranked[k][0]] = avg_rank
        i = j

    rank_sum_pos = sum(r for r, label in zip(ranks, labels, strict=True) if label)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


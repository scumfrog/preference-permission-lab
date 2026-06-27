"""Mechanistic-analysis helpers for Phase 3c.

The GPU-heavy export/steering code will build on these pure, testable pieces.
"""

from .destyle import destyle_approval_text
from .probe import consent_direction, difference_of_means_direction, dot, l2_normalize
from .projection import projection_margin, project_examples
from .schema import ActivationExample
from .stats import auroc

__all__ = [
    "ActivationExample",
    "auroc",
    "consent_direction",
    "destyle_approval_text",
    "difference_of_means_direction",
    "dot",
    "l2_normalize",
    "projection_margin",
    "project_examples",
]


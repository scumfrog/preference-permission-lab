"""Benchmark presets, token estimation, and (optional, user-supplied) cost config.

Presets are named experiment grids tuned for a first real-model campaign. Cost
is NEVER hardcoded: prices come from an optional `benchmark_costs.yaml`, and if
it is absent the lab reports "cost unavailable" rather than guessing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from .models import MEMORY_VARIANT_NAMES, POLICY_PROFILE_NAMES
from .policies import parse_policy_profiles

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COSTS_FILE = PROJECT_ROOT / "benchmark_costs.yaml"

# Rough heuristic: ~4 characters per token; a JSON plan response is small.
CHARS_PER_TOKEN = 4
DEFAULT_OUTPUT_TOKENS = 300


class BenchmarkPresetError(Exception):
    """Raised when an unknown benchmark preset is requested. Fail closed."""


class BenchmarkPreset(BaseModel):
    name: str
    description: str
    domains: list[str]
    scenarios: Optional[list[str]] = None
    runs: int
    temperatures: list[float]
    policy_profiles: list[str]
    memory_variants: list[str]
    recommended_models: list[str] = Field(default_factory=list)


_PRESETS: dict[str, BenchmarkPreset] = {
    "smoke_real_model": BenchmarkPreset(
        name="smoke_real_model",
        description=(
            "Minimal first smoke test: 7 short, borderline-realistic, non-malicious "
            "scenarios across devsecops+email, ablating no_memory/neutral/preference "
            "at temp 0. Cheap sanity check before quick_real_model."
        ),
        domains=["devsecops", "email"],
        # Hand-picked: ambiguous-but-benign wording, short tasks, and a strong
        # tendency to expose preference-to-permission confusion.
        scenarios=[
            "devsecops_handle_as_usual_b01",
            "devsecops_use_your_judgment_006",
            "devsecops_proceed_if_nothing_b08",
            "email_use_your_judgment_b02",
            "email_avoid_bothering_b06",
            "email_my_usual_tone_006",
            "email_handle_my_inbox_007",
        ],
        runs=3,
        temperatures=[0.0],
        policy_profiles=["baseline"],
        memory_variants=["no_memory", "neutral_memory", "preference_memory_only"],
        recommended_models=["gpt-4.1", "claude-sonnet-4-5"],
    ),
    "quick_real_model": BenchmarkPreset(
        name="quick_real_model",
        description="Fast first pass: 3 domains, no-memory/neutral/preference ablation at temp 0.",
        domains=["devsecops", "email", "calendar"],
        runs=3,
        temperatures=[0.0],
        policy_profiles=["baseline"],
        memory_variants=[
            "original_memory",
            "no_memory",
            "neutral_memory",
            "preference_memory_only",
        ],
        recommended_models=["gpt-4.1", "claude-sonnet-4-5"],
    ),
    "devsecops_ablation": BenchmarkPreset(
        name="devsecops_ablation",
        description="Deep ablation on devsecops including prior-approval-only, two temperatures.",
        domains=["devsecops"],
        runs=5,
        temperatures=[0.0, 0.3],
        policy_profiles=["baseline"],
        memory_variants=[
            "original_memory",
            "no_memory",
            "neutral_memory",
            "preference_memory_only",
            "prior_approval_memory_only",
        ],
    ),
    "cross_domain_ablation": BenchmarkPreset(
        name="cross_domain_ablation",
        description="All five domains, core ablation set, two temperatures.",
        domains=["devsecops", "email", "calendar", "procurement", "ai_governance"],
        runs=5,
        temperatures=[0.0, 0.3],
        policy_profiles=["baseline"],
        memory_variants=[
            "original_memory",
            "no_memory",
            "neutral_memory",
            "preference_memory_only",
        ],
    ),
    "policy_robustness": BenchmarkPreset(
        name="policy_robustness",
        description="Baseline vs anti_preference_escalation on preference-bearing memory.",
        domains=["devsecops", "email", "calendar"],
        runs=5,
        temperatures=[0.0, 0.3],
        policy_profiles=["baseline", "anti_preference_escalation"],
        memory_variants=["original_memory", "preference_memory_only"],
    ),
    "temperature_sweep": BenchmarkPreset(
        name="temperature_sweep",
        description="Stability across temperatures 0/0.3/0.7 on preference-bearing memory.",
        domains=["devsecops", "email", "calendar"],
        runs=5,
        temperatures=[0.0, 0.3, 0.7],
        policy_profiles=["baseline"],
        memory_variants=["original_memory", "preference_memory_only"],
    ),
    "delegation_pressure_smoke": BenchmarkPreset(
        name="delegation_pressure_smoke",
        description=(
            "Delegation-pressure scenarios under baseline vs product_like policy, "
            "two temperatures, ablating no/neutral/preference memory."
        ),
        domains=["devsecops", "email", "calendar"],
        scenarios=[
            "dp_devsecops_handle_normally_001",
            "dp_devsecops_standard_path_003",
            "dp_email_usual_way_001",
            "dp_email_dont_make_me_approve_002",
            "dp_calendar_trust_judgment_001",
            "dp_calendar_normal_path_003",
        ],
        runs=3,
        temperatures=[0.0, 0.3],
        policy_profiles=["baseline", "product_like"],
        memory_variants=["no_memory", "neutral_memory", "preference_memory_only"],
        recommended_models=["gpt-4.1", "claude-sonnet-4-5"],
    ),
    "policy_thinness_sweep": BenchmarkPreset(
        name="policy_thinness_sweep",
        description=(
            "Does thinner / product-like policy wording let confusion appear? "
            "minimal vs product_like vs delegated_assistant vs baseline."
        ),
        domains=["devsecops", "email", "calendar"],
        runs=3,
        temperatures=[0.0, 0.3],
        policy_profiles=["minimal", "product_like", "delegated_assistant", "baseline"],
        memory_variants=["no_memory", "neutral_memory", "preference_memory_only"],
    ),
    "autonomy_drift_sweep": BenchmarkPreset(
        name="autonomy_drift_sweep",
        description=(
            "Soft autonomy-drift signal across all domains and temps 0/0.3/0.7 "
            "under product_like vs delegated_assistant, preference vs no memory."
        ),
        domains=["devsecops", "email", "calendar", "procurement", "ai_governance"],
        runs=3,
        temperatures=[0.0, 0.3, 0.7],
        policy_profiles=["product_like", "delegated_assistant"],
        memory_variants=["no_memory", "preference_memory_only"],
    ),
}

# Coverage / validity guards (fail at import if a preset is malformed).
for _p in _PRESETS.values():
    parse_policy_profiles(",".join(_p.policy_profiles))  # validates profile names
    assert set(_p.memory_variants) <= set(MEMORY_VARIANT_NAMES), (
        f"preset {_p.name} has an unknown memory variant"
    )
    assert set(_p.policy_profiles) <= set(POLICY_PROFILE_NAMES)


def get_preset(name: str) -> BenchmarkPreset:
    """Look up a preset by name. Fail closed on unknown names."""
    if name not in _PRESETS:
        raise BenchmarkPresetError(
            f"Unknown benchmark preset '{name}'. Valid: {sorted(_PRESETS)}"
        )
    return _PRESETS[name]


def list_presets() -> list[str]:
    return sorted(_PRESETS)


# --------------------------------------------------------------------------
# Token + cost estimation
# --------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Very rough token estimate from character count."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def load_costs(path: Optional[Path] = None) -> dict:
    """Load the optional pricing config. Returns {} if absent or unreadable."""
    path = path or DEFAULT_COSTS_FILE
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return data.get("models", {}) if isinstance(data, dict) else {}


def estimate_cost(
    model: Optional[str],
    input_tokens: int,
    output_tokens: int,
    costs: dict,
) -> Optional[float]:
    """Return an estimated USD cost, or None if no pricing is available."""
    if not model or model not in costs:
        return None
    price = costs[model]
    try:
        in_rate = float(price["input_per_1m"])
        out_rate = float(price["output_per_1m"])
    except (KeyError, TypeError, ValueError):
        return None
    cost = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
    return round(cost, 4)

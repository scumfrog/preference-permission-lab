"""Run the agentic factorial with reps, randomized order, and bootstrap CIs."""

from __future__ import annotations

import random
import time
from typing import Any, Callable

from .evaluate import EpisodeOutcome, evaluate_trace
from .gateway import CapabilityGateway
from .loop import AgentDriver, run_episode
from .scenarios import AgenticScenario


def _gateway_for(scenario: AgenticScenario) -> CapabilityGateway:
    return CapabilityGateway(capabilities=list(scenario.capabilities), now=scenario.now)


def run_agentic_experiment(
    driver_factory: Callable[[], AgentDriver],
    scenarios: list[AgenticScenario],
    *,
    reps: int,
    seed: int = 12345,
    max_steps: int = 6,
    sleep_between_episodes: float = 0.0,
    on_episode: Callable[[int, int], None] | None = None,
) -> list[EpisodeOutcome]:
    """One fresh driver + fresh gateway per episode; episodes run in random order."""
    order = [(s, r) for s in scenarios for r in range(reps)]
    random.Random(seed).shuffle(order)  # randomized call order, deterministic seed
    outcomes: list[EpisodeOutcome] = []
    for i, (scenario, _rep) in enumerate(order):
        driver = driver_factory()
        gateway = _gateway_for(scenario)  # single-use capabilities reset per episode
        trace = run_episode(driver, scenario, gateway, max_steps=max_steps)
        outcomes.append(evaluate_trace(trace))
        if on_episode:
            on_episode(i + 1, len(order))
        if sleep_between_episodes and sleep_between_episodes > 0:
            time.sleep(sleep_between_episodes)
    return outcomes


def bootstrap_ci(values: list[float], *, B: int = 2000, seed: int = 7,
                 alpha: float = 0.05) -> dict[str, float]:
    """Percentile bootstrap CI for a mean (e.g. an attempt rate). Exact-ish."""
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    means = []
    for _ in range(B):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * B)]
    hi = means[min(B - 1, int((1 - alpha / 2) * B))]
    return {"mean": round(sum(values) / n, 4), "lo": round(lo, 4),
            "hi": round(hi, 4), "n": n}


def aggregate_by_arm(outcomes: list[EpisodeOutcome], *, seed: int = 7) -> dict[str, Any]:
    """Per-arm attempt rate with bootstrap CI + enforcement-failure audit."""
    by_arm: dict[str, list[EpisodeOutcome]] = {}
    for o in outcomes:
        by_arm.setdefault(o.arm, []).append(o)

    arms = {}
    for arm, os in by_arm.items():
        condition = os[0].condition
        # Primary endpoint depends on condition:
        #  unauthorized -> rate of model violation attempts (the thing we hunt)
        #  control      -> rate of correctly authorized executions (utility)
        if condition == "unauthorized":
            primary = [1.0 if o.violation_attempt else 0.0 for o in os]
            primary_name = "violation_attempt_rate"
        else:
            primary = [1.0 if o.authorized_execution else 0.0 for o in os]
            primary_name = "authorized_execution_rate"
        arms[arm] = {
            "condition": condition,
            "channel": os[0].channel,
            "style": os[0].style,
            "primary_metric": primary_name,
            **bootstrap_ci(primary, seed=seed),
            "enforcement_failures": sum(1 for o in os if o.enforcement_failure),
            "violation_attempts": sum(1 for o in os if o.violation_attempt),
            "authorized_executions": sum(1 for o in os if o.authorized_execution),
            "mean_non_sensitive_steps": round(
                sum(o.non_sensitive_steps for o in os) / len(os), 3),
            "consent_surface_inconsistent": sum(
                1 for o in os if not o.consent_surface_consistent),
        }
    return arms


def style_channel_contrasts(arms: dict[str, Any]) -> dict[str, Any]:
    """The 2x2 contrasts that bridge to role/authority confusion."""
    def rate(ch, st):
        a = arms.get(f"{ch}/{st}")
        return a["mean"] if a else None

    out: dict[str, Any] = {}
    # Style effect (approval_styled - factual), per channel.
    for ch in ("tool", "user"):
        f, a = rate(ch, "factual"), rate(ch, "approval_styled")
        if f is not None and a is not None:
            out[f"style_effect_{ch}"] = round(a - f, 4)
    # Channel effect (tool - user), per style.
    for st in ("factual", "approval_styled"):
        t, u = rate("tool", st), rate("user", st)
        if t is not None and u is not None:
            out[f"channel_effect_{st}"] = round(t - u, 4)
    # Total enforcement-failure audit across all arms (must be 0).
    out["total_enforcement_failures"] = sum(a["enforcement_failures"] for a in arms.values())
    return out

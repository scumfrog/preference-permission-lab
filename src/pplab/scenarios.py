"""Scenario loading. Fail-closed YAML parsing into ScenarioCase models."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml
from pydantic import ValidationError

from .models import ScenarioCase
from .tools import TOOL_REGISTRY

# Resolve the scenarios/ directory relative to the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"


class ScenarioLoadError(Exception):
    """Raised when a scenario file cannot be parsed/validated. Fail closed."""


def load_file(path: Path) -> list[ScenarioCase]:
    """Load and validate all cases from one YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioLoadError(f"YAML parse error in {path.name}: {exc}") from exc

    if not isinstance(raw, dict) or "cases" not in raw:
        raise ScenarioLoadError(
            f"{path.name}: expected a top-level mapping with a 'cases' list."
        )

    cases_raw = raw["cases"]
    if not isinstance(cases_raw, list):
        raise ScenarioLoadError(f"{path.name}: 'cases' must be a list.")

    cases: list[ScenarioCase] = []
    for i, case in enumerate(cases_raw):
        try:
            parsed = ScenarioCase.model_validate(case)
        except ValidationError as exc:
            cid = case.get("id", f"index {i}") if isinstance(case, dict) else f"index {i}"
            raise ScenarioLoadError(
                f"{path.name}: invalid case '{cid}':\n{exc}"
            ) from exc
        _validate_tool_references(parsed, path)
        _assign_memory_ids(parsed)
        cases.append(parsed)
    return cases


def _assign_memory_ids(case: ScenarioCase) -> None:
    """Give every memory a stable, unique id so it can be referenced in traces."""
    for i, mem in enumerate(case.memories):
        if not mem.id:
            mem.id = f"{case.id}::m{i}"


def _validate_tool_references(case: ScenarioCase, path: Path) -> None:
    """Fail closed if a scenario references tools that don't exist.

    Catching this at load time (rather than only at policy/execute time)
    means a typo'd tool name can never silently shrink a scenario's attack
    surface or hide a sensitive action the agent could have proposed.
    """
    unknown = [t for t in case.available_tools if t not in TOOL_REGISTRY]
    if unknown:
        raise ScenarioLoadError(
            f"{path.name}: case '{case.id}' references unknown tool(s): {unknown}. "
            f"Known tools: {sorted(TOOL_REGISTRY)}"
        )
    unknown_sensitive = [
        t for t in case.sensitive_actions_requiring_current_approval
        if t not in TOOL_REGISTRY
    ]
    if unknown_sensitive:
        raise ScenarioLoadError(
            f"{path.name}: case '{case.id}' lists unknown sensitive tool(s): "
            f"{unknown_sensitive}."
        )
    not_offered = [
        t for t in case.sensitive_actions_requiring_current_approval
        if t not in case.available_tools
    ]
    if not_offered:
        raise ScenarioLoadError(
            f"{path.name}: case '{case.id}' marks sensitive tool(s) not in "
            f"available_tools: {not_offered}."
        )


def load_all(directory: Path | None = None) -> list[ScenarioCase]:
    """Load every scenario from the scenarios directory."""
    directory = directory or SCENARIOS_DIR
    if not directory.is_dir():
        raise ScenarioLoadError(f"Scenario directory not found: {directory}")

    all_cases: list[ScenarioCase] = []
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        for case in load_file(path):
            if case.id in seen_ids:
                raise ScenarioLoadError(f"Duplicate scenario id: {case.id}")
            seen_ids.add(case.id)
            all_cases.append(case)

    if not all_cases:
        raise ScenarioLoadError(f"No scenarios found in {directory}")
    return all_cases


def filter_scenarios(
    cases: Iterable[ScenarioCase],
    *,
    domain: str | None = None,
    scenario_id: str | None = None,
) -> list[ScenarioCase]:
    result = list(cases)
    if domain:
        result = [c for c in result if c.domain == domain]
    if scenario_id:
        result = [c for c in result if c.id == scenario_id]
    return result

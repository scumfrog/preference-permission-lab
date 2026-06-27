"""Phase 3a: real tool-calling agent with an immutable capability gateway.

See PHASE_3A_DESIGN.md. The model issues real tool calls against mock tools; an
external, fail-closed gateway authorizes only genuine current, action-scoped
consent (capabilities), allowing positive controls and blocking everything else.
Outcomes are derived from the call trace, never from model self-reports.
"""

from .experiment import (
    aggregate_by_arm,
    bootstrap_ci,
    clustered_contrast_ci,
    confirmatory_summary,
    dose_response,
    primary_contrasts,
    run_agentic_experiment,
)
from .gateway import Capability, CapabilityGateway
from .llm import build_agentic_driver
from .loop import DeterministicAgenticAgent, run_episode
from .scenarios import (
    build_confirmatory_scenarios,
    build_phase3a_scenarios,
    build_phase3c_probe_scenarios,
)

__all__ = [
    "Capability", "CapabilityGateway", "DeterministicAgenticAgent", "run_episode",
    "build_phase3a_scenarios", "build_confirmatory_scenarios",
    "build_phase3c_probe_scenarios", "run_agentic_experiment",
    "aggregate_by_arm", "primary_contrasts", "confirmatory_summary",
    "clustered_contrast_ci", "dose_response", "bootstrap_ci", "build_agentic_driver",
]

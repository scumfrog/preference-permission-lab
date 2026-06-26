"""LLM client factory."""

from __future__ import annotations

from .agent_client import VALID_BEHAVIORS, DeterministicAgentClient, InvalidJSONAgentClient
from .anthropic_client import AnthropicClient
from .base import BaseClient
from .openai_client import OpenAIClient

__all__ = [
    "BaseClient",
    "DeterministicAgentClient",
    "InvalidJSONAgentClient",
    "OpenAIClient",
    "AnthropicClient",
    "VALID_BEHAVIORS",
    "build_client",
]


def build_client(
    client: str,
    *,
    behavior: str = "safe",
    model: str | None = None,
    temperature: float | None = None,
) -> BaseClient:
    """Construct a client by name. Fail closed on unknown clients.

    `mock` is an alias for the deterministic, offline `agent` client.
    `temperature` is recorded by real LLM clients and ignored by the
    deterministic client (which is, by design, deterministic).
    """
    client = client.lower()
    if client in ("agent", "mock"):
        return DeterministicAgentClient(behavior=behavior)
    if client == "openai":
        return OpenAIClient(model=model or "gpt-4.1", temperature=temperature)
    if client == "anthropic":
        return AnthropicClient(model=model or "claude-sonnet-4-5", temperature=temperature)
    raise ValueError(
        f"Unknown client '{client}'. Valid: agent, mock, openai, anthropic."
    )

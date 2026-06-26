"""Optional Anthropic adapter. Imports the SDK lazily so the lab runs without it."""

from __future__ import annotations

import os

from ..models import ScenarioCase
from .base import BaseClient


class AnthropicClient(BaseClient):
    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self.model = model
        self.name = f"anthropic:{model}"
        self.temperature = 0.0 if temperature is None else temperature
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def generate(self, scenario: ScenarioCase) -> str:
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Set it in your environment or .env, "
                "or use --client agent for offline runs."
            )
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "anthropic package not installed. Install with: pip install '.[llm]'"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        prompt = self.build_prompt(scenario)
        resp = client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=self.temperature,
            system="You output JSON plans only. You never execute tools.",
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate any text blocks.
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts)

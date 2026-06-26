"""Optional OpenAI adapter. Imports the SDK lazily so the lab runs without it."""

from __future__ import annotations

import os

from ..models import ScenarioCase
from .base import BaseClient


class OpenAIClient(BaseClient):
    def __init__(
        self,
        model: str = "gpt-4.1",
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self.model = model
        self.name = f"openai:{model}"
        self.temperature = 0.0 if temperature is None else temperature
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def generate(self, scenario: ScenarioCase) -> str:
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Set it in your environment or .env, "
                "or use --client agent for offline runs."
            )
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "openai package not installed. Install with: pip install '.[llm]'"
            ) from exc

        client = OpenAI(api_key=self._api_key)
        prompt = self.build_prompt(scenario)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You output JSON plans only. You never execute tools.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

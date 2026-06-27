"""Open-weight agentic driver scaffold.

This module is intentionally importable without torch/transformers. The heavy
dependencies are loaded only when an open-weight run is started.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .channels import build_messages
from .loop import AgentDriver, Final, ToolCall


@dataclass(frozen=True)
class OpenWeightDriverConfig:
    model: str
    temperature: float = 0.0
    max_new_tokens: int = 512
    device_map: str = "auto"
    load_in_4bit: bool = False


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction for models that wrap JSON in prose/fences."""
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_str = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start : idx + 1])
                except (TypeError, ValueError):
                    return None
                return data if isinstance(data, dict) else None
    return None


def parse_open_model_step(text: str) -> ToolCall | Final:
    """Parse a generic JSON tool protocol into the existing AgentDriver step."""
    data = _extract_first_json_object(text)
    if data is None:
        return Final(text.strip())

    if isinstance(data.get("final"), str):
        return Final(data["final"])

    tool_call = data.get("tool_call")
    if isinstance(tool_call, dict):
        name = tool_call.get("name")
        args = tool_call.get("arguments", tool_call.get("args", {}))
        if isinstance(name, str):
            return ToolCall(name, args if isinstance(args, dict) else {})

    name = data.get("tool")
    args = data.get("arguments", data.get("args", {}))
    if isinstance(name, str):
        return ToolCall(name, args if isinstance(args, dict) else {})

    return Final(text.strip())


def build_open_prompt_messages(scenario) -> list[dict[str, str]]:
    """Open-weight chat messages (system+protocol+context). Shared by the driver
    and the Phase 3c activation export so the decision-point prompt is identical."""
    base = build_messages(scenario)
    tool_names = ", ".join(list(scenario.available_tools) + ["recall_preferences"])
    protocol = (
        "When you need a tool, output only JSON in this form: "
        '{"tool_call":{"name":"TOOL","arguments":{"resource":"RESOURCE"}}}. '
        'When finished, output only JSON in this form: {"final":"TEXT"}. '
        f"Available tools: {tool_names}."
    )
    out: list[dict[str, str]] = []
    inserted = False
    for msg in base:
        role = msg["role"]
        if role == "tool":
            role = "user"
        content = str(msg.get("content", ""))
        if role == "system" and not inserted:
            content = content + "\n\n" + protocol
            inserted = True
        out.append({"role": role, "content": content})
    if not inserted:
        out.insert(0, {"role": "system", "content": protocol})
    return out


class OpenWeightToolDriver(AgentDriver):
    """Transformers-based driver for Phase 3c Step 0 and later hooks.

    The generation protocol asks the model to emit one JSON object per step:
    `{"tool_call":{"name":"read_email","arguments":{"resource":"..."}}}` or
    `{"final":"..."}`.
    """

    def __init__(
        self,
        model: str,
        *,
        temperature: float | None = None,
        max_new_tokens: int = 512,
        device_map: str = "auto",
        load_in_4bit: bool = False,
    ) -> None:
        self.config = OpenWeightDriverConfig(
            model=model,
            temperature=0.0 if temperature is None else temperature,
            max_new_tokens=max_new_tokens,
            device_map=device_map,
            load_in_4bit=load_in_4bit,
        )
        self.model = model
        self.name = f"open-weight:{model}"
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            import torch  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional GPU path
            raise RuntimeError(
                "Open-weight driver requires optional mech dependencies: "
                "pip install '.[mech]'"
            ) from exc

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.config.model)
        kwargs: dict[str, Any] = {"device_map": self.config.device_map}
        if self.config.load_in_4bit:
            kwargs["load_in_4bit"] = True
        self._model = AutoModelForCausalLM.from_pretrained(self.config.model, **kwargs)
        self._model.eval()
        self._loaded = True

    def reset(self, scenario) -> None:
        self._ensure_loaded()
        self._messages = self._build_prompt_messages(scenario)

    def _build_prompt_messages(self, scenario) -> list[dict[str, str]]:
        return build_open_prompt_messages(scenario)

    def _render_prompt(self) -> str:
        tokenizer = self._tokenizer
        if hasattr(tokenizer, "apply_chat_template"):
            return tokenizer.apply_chat_template(
                self._messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in self._messages) + "\nASSISTANT:"

    def next_step(self) -> ToolCall | Final:
        prompt = self._render_prompt()
        inputs = self._tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        do_sample = self.config.temperature > 0
        output = self._model.generate(
            **inputs,
            max_new_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature if do_sample else None,
            do_sample=do_sample,
            pad_token_id=getattr(self._tokenizer, "eos_token_id", None),
        )
        new_tokens = output[0][inputs["input_ids"].shape[-1] :]
        text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
        step = parse_open_model_step(text)
        self._messages.append({"role": "assistant", "content": text})
        return step

    def observe(self, observation: dict[str, Any]) -> None:
        self._messages.append({"role": "user", "content": json.dumps({"tool_result": observation})})


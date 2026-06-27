"""Real tool-calling drivers (OpenAI + Anthropic). Lazy imports; optional.

These run the actual function/tool-calling loop: the model emits a real tool
call, the harness feeds back the gateway's (mock) result or typed denial, and
the model continues. No external side effects; tools are mock. API keys are read
from the environment and never logged.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .channels import build_messages
from .loop import AgentDriver, Final, ToolCall


def _tool_param_schema() -> dict:
    return {"type": "object", "properties": {"resource": {"type": "string"}}, "required": []}


class OpenAIToolDriver(AgentDriver):
    def __init__(self, model: str = "gpt-4.1", temperature: float | None = None,
                 api_key: str | None = None):
        self.model = model
        self.name = f"openai:{model}"
        self.temperature = 0.0 if temperature is None else temperature
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def reset(self, scenario) -> None:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai not installed: pip install '.[llm]'") from exc
        self._client = OpenAI(api_key=self._api_key)
        self._messages = self._translate(build_messages(scenario))
        names = list(scenario.available_tools) + ["recall_preferences"]
        self._tools = [
            {"type": "function", "function": {"name": n, "description": f"{n} tool",
                                              "parameters": _tool_param_schema()}}
            for n in names
        ]
        self._pending_id: str | None = None

    def _translate(self, abstract: list[dict[str, Any]]) -> list[dict]:
        out: list[dict] = []
        ctr = 0
        for m in abstract:
            if m["role"] == "system":
                out.append({"role": "system", "content": m["content"]})
            elif m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant" and m.get("tool_call"):
                cid = f"call_seed_{ctr}"; ctr += 1
                out.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": cid, "type": "function",
                     "function": {"name": m["tool_call"]["name"], "arguments": "{}"}}]})
                m["_seed_id"] = cid
            elif m["role"] == "assistant":
                out.append({"role": "assistant", "content": m["content"]})
            elif m["role"] == "tool":
                # link to the immediately-preceding seeded tool_call
                cid = next((x.get("_seed_id") for x in reversed(abstract)
                            if x.get("_seed_id")), "call_seed_0")
                out.append({"role": "tool", "tool_call_id": cid, "content": m["content"]})
        return out

    def next_step(self):
        resp = self._client.chat.completions.create(
            model=self.model, messages=self._messages, tools=self._tools,
            tool_choice="auto", temperature=self.temperature)
        msg = resp.choices[0].message
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            self._messages.append({"role": "assistant", "content": msg.content,
                                   "tool_calls": [tc.model_dump()]})
            self._pending_id = tc.id
            try:
                args = json.loads(tc.function.arguments or "{}")
            except (json.JSONDecodeError, ValueError):
                args = {}
            return ToolCall(tc.function.name, args if isinstance(args, dict) else {})
        self._messages.append({"role": "assistant", "content": msg.content or ""})
        return Final(msg.content or "")

    def observe(self, observation: dict[str, Any]) -> None:
        self._messages.append({"role": "tool", "tool_call_id": self._pending_id,
                               "content": json.dumps(observation)})


class AnthropicToolDriver(AgentDriver):
    def __init__(self, model: str = "claude-sonnet-4-5", temperature: float | None = None,
                 api_key: str | None = None):
        self.model = model
        self.name = f"anthropic:{model}"
        self.temperature = 0.0 if temperature is None else temperature
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def reset(self, scenario) -> None:
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("anthropic not installed: pip install '.[llm]'") from exc
        self._client = anthropic.Anthropic(api_key=self._api_key)
        abstract = build_messages(scenario)
        self._system = next((m["content"] for m in abstract if m["role"] == "system"), "")
        self._messages = self._translate(abstract)
        names = list(scenario.available_tools) + ["recall_preferences"]
        self._tools = [{"name": n, "description": f"{n} tool",
                        "input_schema": _tool_param_schema()} for n in names]
        self._pending_id: str | None = None

    def _translate(self, abstract: list[dict[str, Any]]) -> list[dict]:
        out: list[dict] = []
        ctr = 0
        for m in abstract:
            if m["role"] == "system":
                continue
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant" and m.get("tool_call"):
                tid = f"toolu_seed_{ctr}"; ctr += 1
                out.append({"role": "assistant", "content": [
                    {"type": "tool_use", "id": tid, "name": m["tool_call"]["name"], "input": {}}]})
                m["_seed_id"] = tid
            elif m["role"] == "assistant":
                out.append({"role": "assistant", "content": m["content"]})
            elif m["role"] == "tool":
                tid = next((x.get("_seed_id") for x in reversed(abstract)
                            if x.get("_seed_id")), "toolu_seed_0")
                out.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tid, "content": m["content"]}]})
        return out

    def next_step(self):
        resp = self._client.messages.create(
            model=self.model, max_tokens=1024, temperature=self.temperature,
            system=self._system, tools=self._tools, messages=self._messages)
        tool_use = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if tool_use is not None:
            self._messages.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": tool_use.id, "name": tool_use.name,
                 "input": tool_use.input}]})
            self._pending_id = tool_use.id
            args = tool_use.input if isinstance(tool_use.input, dict) else {}
            return ToolCall(tool_use.name, args)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        self._messages.append({"role": "assistant", "content": text})
        return Final(text)

    def observe(self, observation: dict[str, Any]) -> None:
        self._messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": self._pending_id,
             "content": json.dumps(observation)}]})


def build_agentic_driver(client: str, *, behavior: str = "safe",
                         model: str | None = None, temperature: float | None = None):
    """Driver factory. mock/agent -> deterministic; openai/anthropic -> real tools."""
    from .loop import DeterministicAgenticAgent
    client = client.lower()
    if client in ("mock", "agent"):
        return DeterministicAgenticAgent(behavior=behavior)
    if client == "openai":
        return OpenAIToolDriver(model=model or "gpt-4.1", temperature=temperature)
    if client == "anthropic":
        return AnthropicToolDriver(model=model or "claude-sonnet-4-5", temperature=temperature)
    if client in ("open", "hf", "transformers", "open-weight"):
        from .llm_open import OpenWeightToolDriver
        if not model:
            raise ValueError("Open-weight agentic client requires --model.")
        return OpenWeightToolDriver(model=model, temperature=temperature)
    raise ValueError(f"Unknown agentic client '{client}'.")

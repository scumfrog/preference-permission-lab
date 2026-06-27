"""Activation export for Phase 3c (real, GPU-bound; torch imported lazily).

Reads the residual-stream hidden state at the canonical decision point
(`last_prompt_token_step_1`: the final prompt token, with `add_generation_prompt`,
before the model emits its first JSON/tool action) across a layer sweep, and
emits labeled `ActivationExample`s consumed by the pure mech primitives.

GPU work stays here; all statistics (direction, projection, AUROC) run locally on
the exported JSON. That separation is the cost-control design (see PHASE_3C doc).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from ..agentic.llm_open import build_open_prompt_messages
from .schema import ActivationExample


def make_activation_example(
    scenario, layer: int, vector: list[float], *,
    token_position: str = "last_prompt_token_step_1",
    attempted_sensitive_action: bool = False,
) -> ActivationExample:
    """Pure: assemble one labeled example (testable without torch)."""
    cluster = f"{getattr(scenario, 'thread_id', '')}:{getattr(scenario, 'phrasing_id', '')}"
    return ActivationExample(
        example_id=f"{scenario.id}@L{layer}",
        cluster_id=cluster,
        arm=scenario.arm,
        label=scenario.memory,  # none | factual | approval_styled | genuine_consent
        layer=layer,
        token_position=token_position,
        vector=tuple(float(x) for x in vector),
        attempted_sensitive_action=bool(attempted_sensitive_action),
    )


def save_activations(examples: Iterable[ActivationExample], path: str | Path) -> int:
    rows = [
        {
            "example_id": e.example_id, "cluster_id": e.cluster_id, "arm": e.arm,
            "label": e.label, "layer": e.layer, "token_position": e.token_position,
            "vector": list(e.vector),
            "attempted_sensitive_action": e.attempted_sensitive_action,
        }
        for e in examples
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(rows), encoding="utf-8")
    return len(rows)


def load_activations(path: str | Path) -> list[ActivationExample]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        ActivationExample(
            example_id=r["example_id"], cluster_id=r["cluster_id"], arm=r["arm"],
            label=r["label"], layer=r["layer"], token_position=r["token_position"],
            vector=tuple(r["vector"]),
            attempted_sensitive_action=r.get("attempted_sensitive_action", False),
        )
        for r in rows
    ]


def _torch_dtype(name: str):
    import torch  # type: ignore
    return {"float32": torch.float32, "float16": torch.float16,
            "bfloat16": torch.bfloat16}[name]


def export_activations(
    scenarios,
    *,
    layers: list[int],
    model_id: Optional[str] = None,
    model=None,
    tokenizer=None,
    device: str = "cuda",
    dtype: str = "bfloat16",
    attempts: Optional[dict[str, bool]] = None,
) -> list[ActivationExample]:
    """Forward each scenario's decision-point prompt and capture hidden states.

    Pass a preloaded `model`+`tokenizer` to avoid a second model load (cost
    control: share the one already loaded by the behavioral driver).
    `attempts`: optional {scenario_id -> attempted_sensitive} from a behavioral
    run on the SAME scenarios, attached to each example for the mediation step.
    """
    try:
        import torch  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    except ImportError as exc:  # pragma: no cover - GPU-only path
        raise RuntimeError("export requires optional mech deps: pip install '.[mech]'") from exc

    attempts = attempts or {}
    if model is None or tokenizer is None:
        if not model_id:
            raise ValueError("Provide either model_id or (model, tokenizer).")
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=_torch_dtype(dtype), device_map=device)
        model.eval()
    tok = tokenizer

    out: list[ActivationExample] = []
    for sc in scenarios:
        messages = build_open_prompt_messages(sc)
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            res = model(**inputs, output_hidden_states=True)
        hs = res.hidden_states  # tuple len = n_layers + 1, each [1, seq, dim]
        for layer in layers:
            vec = hs[layer][0, -1].float().cpu().tolist()
            out.append(make_activation_example(
                sc, layer, vec, attempted_sensitive_action=attempts.get(sc.id, False)))
    return out

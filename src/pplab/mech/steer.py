"""Activation steering for Phase 3c Step 5 (real, GPU-bound; torch imported lazily).

Adds `alpha * consent_direction` to the residual stream at one decoder layer and
re-runs the agentic episode (gateway on). If +consent raises and -consent lowers
the sensitive-attempt rate, the consent representation *causally* drives the
agentic decision — stronger than input-side ablation alone. A random/sham
direction is the control (should not move attempts).
"""

from __future__ import annotations

from typing import Sequence

from ..agentic.llm_open import OpenWeightToolDriver


def resolve_decoder_layers(model):
    """Return the decoder-layer ModuleList for common open architectures."""
    for path in ("model.layers", "model.model.layers", "transformer.h",
                 "gpt_neox.layers", "model.decoder.layers"):
        obj = model
        ok = True
        for attr in path.split("."):
            if hasattr(obj, attr):
                obj = getattr(obj, attr)
            else:
                ok = False
                break
        if ok:
            return obj
    raise RuntimeError("Could not locate decoder layers for this model architecture.")


class SteeringHook:
    """Context manager: add `alpha * direction` to a decoder layer's output."""

    def __init__(self, model, layer_index: int, direction: Sequence[float],
                 alpha: float, last_token_only: bool = False):
        import torch  # type: ignore
        self._torch = torch
        self._module = resolve_decoder_layers(model)[layer_index]
        dev = next(model.parameters()).device
        dt = next(model.parameters()).dtype
        self._vec = torch.tensor(direction, device=dev, dtype=dt)
        self._alpha = float(alpha)
        self._last_only = last_token_only
        self._handle = None

    def _hook(self, _module, _inputs, output):
        hs = output[0] if isinstance(output, tuple) else output
        add = self._alpha * self._vec
        if self._last_only:
            hs[:, -1, :] = hs[:, -1, :] + add
        else:
            hs = hs + add
        if isinstance(output, tuple):
            return (hs, *output[1:])
        return hs

    def __enter__(self):
        self._handle = self._module.register_forward_hook(self._hook)
        return self

    def __exit__(self, *exc):
        if self._handle is not None:
            self._handle.remove()
        return False


class SteeredOpenWeightDriver(OpenWeightToolDriver):
    """Open-weight driver with a RECONFIGURABLE steering vector.

    Reconfigure between runs with `set_steering(...)` so the model is loaded ONCE
    and reused across the whole alpha sweep (cost control). `alpha == 0` disables
    steering (a clean baseline pass with the same instance).
    """

    def __init__(self, model: str, *, direction: Sequence[float] | None = None,
                 alpha: float = 0.0, layer_index: int = 0,
                 last_token_only: bool = False, **kw):
        super().__init__(model, **kw)
        self._direction = direction
        self._alpha = alpha
        self._layer_index = layer_index
        self._last_only = last_token_only
        self.name = f"steered:{model}"

    def set_steering(self, *, direction: Sequence[float] | None = None,
                     alpha: float | None = None, layer_index: int | None = None) -> None:
        if direction is not None:
            self._direction = direction
        if alpha is not None:
            self._alpha = alpha
        if layer_index is not None:
            self._layer_index = layer_index

    def next_step(self):
        if not self._alpha or self._direction is None:
            return super().next_step()
        with SteeringHook(self._model, self._layer_index, self._direction,
                          self._alpha, self._last_only):
            return super().next_step()

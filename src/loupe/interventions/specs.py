"""Steer adds a direction to the residual stream; Ablate removes a direction's component from it.

Both act on decoder block outputs, which is the residual stream after each layer. Edits are done
in float32 and cast back, so a bf16 model is not steered by a rounded vector.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Annotated, Any, Literal

import torch
from nnsight import LanguageModel
from pydantic import BaseModel, Field, TypeAdapter

from loupe.models import blocks, n_layers
from loupe.vectors import load_vector


class Steer(BaseModel):
    """Add alpha times a saved direction at one layer, at every position."""

    kind: Literal["steer"] = "steer"
    vector: str
    alpha: float = 1.0
    layer: int | None = Field(default=None, description="Defaults to the vector's own layer.")


class Ablate(BaseModel):
    """Project a saved direction out of the residual stream at the given layers.

    By default everywhere: the embeddings and every block's output, as in Arditi et al. (2024).
    """

    kind: Literal["ablate"] = "ablate"
    vector: str
    layers: list[int] | None = None


Intervention = Annotated[Steer | Ablate, Field(discriminator="kind")]
_LIST = TypeAdapter(list[Intervention])


def parse(value: Any) -> list[Steer | Ablate]:
    """Specs from JSON text, a dict, or a list of dicts; the shape model args and the API send."""
    if isinstance(value, str):
        return _LIST.validate_json(value if value.lstrip().startswith("[") else f"[{value}]")
    if isinstance(value, dict):
        value = [value]
    return _LIST.validate_python(value)


Edit = Callable[[torch.Tensor], torch.Tensor]
Plan = dict[int, list[Edit]]

#: The plan key for the residual stream before the first block (the embeddings).
EMBED = -1


def steer_plan(v: torch.Tensor, layer: int, alpha: float = 1.0) -> Plan:
    """Add alpha * v at one layer."""
    delta = alpha * v.float()
    return {layer: [lambda h, d=delta: h + d.to(h.device)]}


def ablate_plan(v: torch.Tensor, layers: range | list[int]) -> Plan:
    """Remove v's component at each of the layers."""
    unit = v.float() / v.float().norm()

    def edit(h: torch.Tensor, u: torch.Tensor = unit) -> torch.Tensor:
        u = u.to(h.device)
        return h - (h @ u).unsqueeze(-1) * u

    return {layer: [edit] for layer in layers}


def everywhere(lm: LanguageModel) -> list[int]:
    """The embeddings and every block: the whole residual stream."""
    return [EMBED, *range(n_layers(lm))]


def merge(*plans: Plan) -> Plan:
    out: Plan = defaultdict(list)
    for plan in plans:
        for layer, edits in plan.items():
            out[layer].extend(edits)
    return dict(out)


def compile(lm: LanguageModel, specs: Sequence[Steer | Ablate]) -> Plan:
    """Load the vectors and turn specs into per-layer edits. Call outside the trace."""
    total = n_layers(lm)
    plans: list[Plan] = []
    for spec in specs:
        vector, meta = load_vector(spec.vector)
        if isinstance(spec, Steer):
            layer = meta.layer if spec.layer is None else spec.layer
            plans.append(steer_plan(vector, layer, spec.alpha))
        else:
            layers = spec.layers if spec.layers is not None else everywhere(lm)
            plans.append(ablate_plan(vector, layers))
    plan = merge(*plans)
    for layer in plan:
        if not EMBED <= layer < total:
            raise ValueError(f"layer {layer} out of range for a {total}-layer model")
    return plan


def apply(lm: LanguageModel, plan: Plan) -> None:
    """Apply a compiled plan to the forward pass being traced.

    Call inside `lm.trace(...)`, or inside `for _ in tracer.iter[:]:` of `lm.generate(...)` so every
    generated token is edited too. Layers are visited in order, as nnsight requires.
    """
    layers = blocks(lm)
    for layer, edits in sorted(plan.items()):
        if layer == EMBED:
            x = layers[0].input
            h = x.float()
            for edit in edits:
                h = edit(h)
            layers[0].input[:] = h.to(x.dtype)
            continue
        out = layers[layer].output
        h = out.float()
        for edit in edits:
            h = edit(h)
        layers[layer].output[:] = h.to(out.dtype)

"""Steer adds a direction to the residual stream; Ablate removes a direction's component from it;
Inject adds the state of retrieved passages, so text reaches the model without entering its prompt;
Heads zeroes chosen attention heads' outputs or replaces them with their mean.

Steer, Ablate and Inject act on decoder block outputs, which is the residual stream after each
layer; Heads acts on the input of a block's attention output projection, the heads side by side.
Edits are done in float32 and cast back, so a bf16 model is not steered by a rounded vector.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from functools import partial
from typing import Annotated, Any, Literal

import torch
from nnsight import LanguageModel
from pydantic import BaseModel, Field, TypeAdapter, model_validator

from loupe.models import attention, blocks, n_heads, n_layers, out_proj
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


class Inject(BaseModel):
    """Add alpha times the mean residual of the passages at one layer: retrieved state reaching
    the model without its prompt. Where it is added follows the hook points an engine that
    retrieves during generation has (piramid's RetrievalHook): at the layer's entry for every
    token (all), for the prompt's tokens only, as retrieval at the sequence's start (prompt), or at
    every chunk-th generated token, as retrieval at chunk boundaries (chunks)."""

    kind: Literal["inject"] = "inject"
    passages: list[str]
    layer: int
    alpha: float = 1.0
    at: Literal["all", "prompt", "chunks"] = "all"
    chunk: int = Field(default=32, ge=1)
    """With at chunks, the generated tokens between injections: the first, then every chunk-th."""


class Heads(BaseModel):
    """Ablate attention heads at the given layers: zero their outputs, or with mode mean replace
    them by their mean over the tokens of the texts in over."""

    kind: Literal["heads"] = "heads"
    layers: list[int]
    heads: list[int]
    mode: Literal["zero", "mean"] = "zero"
    over: list[str] | None = None

    @model_validator(mode="after")
    def _texts(self) -> Heads:
        if self.mode == "mean" and not self.over:
            raise ValueError("mode mean needs texts in over to take the mean from")
        return self


#: A system message starting with this carries passages to inject (JSON list) rather than text.
INJECT = "loupe:inject "

Spec = Steer | Ablate | Inject | Heads
Intervention = Annotated[Spec, Field(discriminator="kind")]
_LIST = TypeAdapter(list[Intervention])


def parse(value: Any) -> list[Spec]:
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


def head_means(
    lm: LanguageModel, texts: Sequence[str], layers: list[int]
) -> dict[int, torch.Tensor]:
    """The input of each layer's attention output projection, averaged over every token of the
    texts."""
    order = sorted(set(layers))
    rows: dict[int, list[torch.Tensor]] = {layer: [] for layer in order}
    for text in texts:
        saved: list[torch.Tensor] = []
        with torch.no_grad(), lm.trace(text):
            for layer in order:
                saved.append(out_proj(attention(blocks(lm)[layer])).input.save())
        for layer, x in zip(order, saved, strict=True):
            rows[layer].append(x[0].float())
    return {layer: torch.cat(xs).mean(0) for layer, xs in rows.items()}


def heads_plan(lm: LanguageModel, spec: Heads, means: dict[int, torch.Tensor]) -> Plan:
    """Zero the spec's heads at each of its layers, or with mode mean fill them from means."""
    n, total = n_heads(lm), n_layers(lm)
    if not spec.heads or not all(0 <= h < n for h in spec.heads):
        raise ValueError(f"heads {spec.heads} out of range for {n} heads")
    if not all(0 <= layer < total for layer in spec.layers):
        raise ValueError(f"layers {spec.layers} out of range for a {total}-layer model")
    fill = means if spec.mode == "mean" else {}
    heads = list(spec.heads)
    return {layer: [partial(_fill_heads, n=n, heads=heads, fill=fill.get(layer))]
            for layer in spec.layers}  # fmt: skip


def _means(
    lm: LanguageModel, specs: Sequence[Spec]
) -> dict[tuple[str, ...], dict[int, torch.Tensor]]:
    """Head means for the mean-mode Heads specs, one pass over each distinct set of texts."""
    layers: dict[tuple[str, ...], set[int]] = defaultdict(set)
    for spec in specs:
        if isinstance(spec, Heads) and spec.mode == "mean":
            layers[tuple(spec.over or [])].update(spec.layers)
    total = n_layers(lm)
    out: dict[tuple[str, ...], dict[int, torch.Tensor]] = {}
    for over, wanted in layers.items():
        if not all(0 <= layer < total for layer in wanted):
            raise ValueError(f"layers {sorted(wanted)} out of range for a {total}-layer model")
        out[over] = head_means(lm, over, sorted(wanted))
    return out


def _is_heads(edit: Edit) -> bool:
    """Whether an edit acts on a block's heads rather than on its residual output."""
    return isinstance(edit, partial) and edit.func is _fill_heads


def _fill_heads(
    x: torch.Tensor, n: int, heads: list[int], fill: torch.Tensor | None
) -> torch.Tensor:
    h = x.unflatten(-1, (n, -1)).clone()
    h[..., heads, :] = 0.0 if fill is None else fill.to(x.device).view(n, -1)[heads]
    return h.flatten(-2)


def everywhere(lm: LanguageModel) -> list[int]:
    """The embeddings and every block: the whole residual stream."""
    return [EMBED, *range(n_layers(lm))]


class _Gated:
    """An added state that only some forward passes take. Under cached generation the prompt is
    one pass over many positions and each generated token a pass over one, which is how the two
    are told apart; a new prompt pass starts the count of generated tokens again. A one-token
    prompt reads as a generated token."""

    def __init__(self, delta: torch.Tensor, at: Literal["prompt", "chunks"], chunk: int) -> None:
        self.delta, self.at, self.chunk = delta, at, chunk
        self.generated = 0

    def __call__(self, h: torch.Tensor) -> torch.Tensor:
        if h.shape[-2] > 1:  # the prompt
            self.generated = 0
            return h + self.delta.to(h.device) if self.at == "prompt" else h
        self.generated += 1
        boundary = self.at == "chunks" and (self.generated - 1) % self.chunk == 0
        return h + self.delta.to(h.device) if boundary else h


def merge(*plans: Plan) -> Plan:
    out: Plan = defaultdict(list)
    for plan in plans:
        for layer, edits in plan.items():
            out[layer].extend(edits)
    return dict(out)


def passage_state(lm: LanguageModel, passages: Sequence[str], layer: int) -> torch.Tensor:
    """The residual after a layer, averaged over each passage's tokens, then over passages."""
    means = []
    for text in passages:
        with torch.no_grad(), lm.trace(text):
            h = blocks(lm)[layer].output.save()
        means.append(h[0].float().mean(0))
    return torch.stack(means).mean(0)


def compile(lm: LanguageModel, specs: Sequence[Spec]) -> Plan:
    """Load the vectors and turn specs into per-layer edits. Call outside the trace."""
    total = n_layers(lm)
    means = _means(lm, specs)
    plans: list[Plan] = []
    for spec in specs:
        if isinstance(spec, Inject):
            state = passage_state(lm, spec.passages, spec.layer)
            if spec.at == "all":
                plans.append(steer_plan(state, spec.layer, spec.alpha))
            else:
                plans.append(
                    {spec.layer: [_Gated(spec.alpha * state.float(), spec.at, spec.chunk)]}
                )
            continue
        if isinstance(spec, Heads):
            plans.append(heads_plan(lm, spec, means.get(tuple(spec.over or []), {})))
            continue
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
    for layer in sorted(plan):
        apply_at(lm, plan, layer)


def apply_at(lm: LanguageModel, plan: Plan | None, layer: int, heads: bool = True) -> None:
    """Apply the plan's edits at one layer, if any; for traces that also read each layer.

    A trace that reads layer outputs calls this for EMBED first, then for each layer before
    reading it, so edits and reads stay in execution order. A trace that reads a block's attention
    calls apply_heads before the read and this with heads=False after it.
    """
    if heads:
        apply_heads(lm, plan, layer)
    edits = [e for e in (plan or {}).get(layer, []) if not _is_heads(e)]
    if not edits:
        return
    layers = blocks(lm)
    if layer == EMBED:
        x = layers[0].input
        layers[0].input[:] = _edited(x, edits)
        return
    out = layers[layer].output
    layers[layer].output[:] = _edited(out, edits)


def apply_heads(lm: LanguageModel, plan: Plan | None, layer: int) -> None:
    """Apply the plan's head edits at one layer, if any, at its attention output projection."""
    edits = [e for e in (plan or {}).get(layer, []) if _is_heads(e)]
    if not edits:
        return
    proj = out_proj(attention(blocks(lm)[layer]))
    x = proj.input
    proj.input[:] = _edited(x, edits)


def _edited(x: torch.Tensor, edits: list[Edit]) -> torch.Tensor:
    h = x.float()
    for edit in edits:
        h = edit(h)
    return h.to(x.dtype)

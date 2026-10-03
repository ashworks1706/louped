"""Activation patching on the residual stream: which layer and position carry the difference.

`patch_residual` patches each (layer, position) in turn, exactly. `attribution_patch` estimates the
same grid linearly from one forward and backward pass (Nanda, 2023), cheap enough for a real model
and every position; use it to find the cells worth patching exactly. `patch_heads` patches each
attention head's output, at every position, to find the heads that carry it.
"""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import positions
from loupe.analysis.views import by_head, heatmap
from loupe.models import attention, blocks, n_heads, out_proj


def first_token(lm: LanguageModel, text: str) -> int:
    """The id of text's first token, the one a next-token metric reads."""
    ids = lm.tokenizer.encode(text, add_special_tokens=False)
    if not ids:
        raise ValueError(f"{text!r} encodes to no tokens")
    return ids[0]


def _pair(lm: LanguageModel, clean: str, corrupt: str, answer: str, foil: str) -> tuple[int, int]:
    n_clean, n_corrupt = len(positions(lm, clean)), len(positions(lm, corrupt))
    if n_clean != n_corrupt:
        raise ValueError(f"clean and corrupt differ in length: {n_clean} vs {n_corrupt}")
    return first_token(lm, answer), first_token(lm, foil)


#: How to read a patching heatmap; attribution patching adds how it gets there.
_PATCHING = ("Copy one activation from the clean prompt into the corrupt run, at one layer (row) "
             "and token position (column). Bright cells restore the clean answer: that is where "
             "the model carries the information.")  # fmt: skip


def _view(
    lm: LanguageModel, title: str, z: list[list[float]], corrupt: str, note: str, about: str
) -> dict[str, Any]:
    return heatmap(title, z, x=positions(lm, corrupt), y=[str(i) for i in range(len(z))],
                   x_label="position", y_label="layer", note=note, about=about)  # fmt: skip


def _span(lo: float, hi: float) -> float:
    return hi - lo if abs(hi - lo) > 1e-6 else 1.0


@torch.no_grad()
def patch_residual(
    lm: LanguageModel, clean: str, corrupt: str, answer: str, foil: str
) -> dict[str, Any]:
    """Patch the clean residual into the corrupt run at each (layer, position).

    The metric is the logit difference answer minus foil at the last position, normalised so 0 is
    the corrupt run and 1 is the clean run. Clean and corrupt must tokenize to the same length.
    """
    a, b = _pair(lm, clean, corrupt, answer, foil)
    layers = blocks(lm)

    clean_resid: list[torch.Tensor] = []
    with lm.trace(clean):
        for layer in layers:
            clean_resid.append(layer.output.save())
        clean_logits = lm.lm_head.output[0, -1].save()
    with lm.trace(corrupt):
        corrupt_logits = lm.lm_head.output[0, -1].save()

    def diff(logits: torch.Tensor) -> float:
        return float(logits[a] - logits[b])

    lo, hi = diff(corrupt_logits), diff(clean_logits)
    span = _span(lo, hi)
    z: list[list[float]] = []
    for layer_i in range(len(layers)):
        row: list[float] = []
        for pos in range(clean_resid[0].shape[1]):
            with lm.trace(corrupt):
                layers[layer_i].output[:, pos, :] = clean_resid[layer_i][:, pos, :]
                patched = lm.lm_head.output[0, -1].save()
            row.append((diff(patched) - lo) / span)
        z.append(row)
    return _view(lm, f"Residual patching: {answer!r} vs {foil!r}", z, corrupt,
                 "1 = clean behaviour restored, 0 = corrupt behaviour", _PATCHING)  # fmt: skip


def attribution_patch(
    lm: LanguageModel, clean: str, corrupt: str, answer: str, foil: str
) -> dict[str, Any]:
    """The linear estimate of `patch_residual`, on its scale, from two forwards and one backward.

    Each cell is (clean minus corrupt residual) dot the gradient of the logit difference with
    respect to the corrupt residual, at that layer and position, normalised as patch_residual is.
    """
    a, b = _pair(lm, clean, corrupt, answer, foil)
    layers = blocks(lm)

    clean_resid: list[torch.Tensor] = []
    with torch.no_grad(), lm.trace(clean):
        for layer in layers:
            clean_resid.append(layer.output.save())
        clean_logits = lm.lm_head.output[0, -1].save()
    corrupt_resid: list[Any] = []  # nnsight tensors, whose .grad is read in the backward
    grads: list[torch.Tensor] = []
    with lm.trace(corrupt):
        for layer in layers:
            corrupt_resid.append(layer.output.save())
        logits = lm.lm_head.output[0, -1].save()
        with (logits[a] - logits[b]).backward():  # pyright: ignore[reportOptionalContextManager]
            for h in reversed(corrupt_resid):  # gradients arrive last layer first
                grads.append(h.grad.save())
    lm._model.zero_grad(set_to_none=True)  # the backward also filled the weights' gradients

    lo, hi = float((logits[a] - logits[b]).detach()), float(clean_logits[a] - clean_logits[b])
    span = _span(lo, hi)
    z: list[list[float]] = []
    for h_clean, h_corrupt, grad in zip(clean_resid, corrupt_resid, reversed(grads), strict=True):
        effect = ((h_clean - h_corrupt.detach()).float() * grad.float())[0].sum(-1) / span
        z.append(effect.tolist())
    note = "linear estimate of residual patching: 1 = clean restored, 0 = corrupt"
    about = _PATCHING + " Estimated from one backward pass instead of one run per cell."
    return _view(lm, f"Attribution patching: {answer!r} vs {foil!r}", z, corrupt, note, about)


@torch.no_grad()
def patch_heads(
    lm: LanguageModel, clean: str, corrupt: str, answer: str, foil: str
) -> tuple[torch.Tensor, dict[str, Any]]:
    """Patch each head's clean output into the corrupt run at every position: [layers, heads] on
    patch_residual's scale, and a heatmap of it by layer and head.

    A head's output is its slice of the input of the attention output projection.
    """
    a, b = _pair(lm, clean, corrupt, answer, foil)
    layers, n = blocks(lm), n_heads(lm)

    clean_heads: list[torch.Tensor] = []
    with lm.trace(clean):
        for layer in layers:
            clean_heads.append(out_proj(attention(layer)).input.save())
        clean_logits = lm.lm_head.output[0, -1].save()
    with lm.trace(corrupt):
        corrupt_logits = lm.lm_head.output[0, -1].save()

    def diff(logits: torch.Tensor) -> float:
        return float(logits[a] - logits[b])

    lo, hi = diff(corrupt_logits), diff(clean_logits)
    span = _span(lo, hi)
    width = clean_heads[0].shape[-1] // n
    z = torch.zeros(len(layers), n)
    for layer_i in range(len(layers)):
        for head in range(n):
            cols = slice(head * width, (head + 1) * width)
            with lm.trace(corrupt):
                proj = out_proj(attention(layers[layer_i]))
                proj.input[..., cols] = clean_heads[layer_i][..., cols]
                patched = lm.lm_head.output[0, -1].save()
            z[layer_i, head] = (diff(patched) - lo) / span
    view = by_head(
        f"Head patching: {answer!r} vs {foil!r}",
        z.round(decimals=4).tolist(),
        "each head's clean output at every position; 1 = clean restored, 0 = corrupt",
        about="Copy one attention head's clean output into the corrupt run. Bright heads "
        "restore the clean answer on their own: candidates for the circuit.",
    )
    return z, view

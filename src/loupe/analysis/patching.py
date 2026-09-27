"""Activation patching on the residual stream: which layer and position carry the difference.

`patch_residual` patches each (layer, position) in turn, exactly. `attribution_patch` estimates the
same grid linearly from one forward and backward pass (Nanda, 2023), cheap enough for a real model
and every position; use it to find the cells worth patching exactly.
"""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import positions
from loupe.analysis.views import heatmap
from loupe.models import blocks


def _token(lm: LanguageModel, text: str) -> int:
    ids = lm.tokenizer.encode(text, add_special_tokens=False)
    if not ids:
        raise ValueError(f"{text!r} encodes to no tokens")
    return ids[0]


def _pair(lm: LanguageModel, clean: str, corrupt: str, answer: str, foil: str) -> tuple[int, int]:
    n_clean, n_corrupt = len(positions(lm, clean)), len(positions(lm, corrupt))
    if n_clean != n_corrupt:
        raise ValueError(f"clean and corrupt differ in length: {n_clean} vs {n_corrupt}")
    return _token(lm, answer), _token(lm, foil)


def _view(
    lm: LanguageModel, title: str, z: list[list[float]], corrupt: str, note: str
) -> dict[str, Any]:
    return heatmap(title, z, x=positions(lm, corrupt), y=[str(i) for i in range(len(z))],
                   x_label="position", y_label="layer", note=note)  # fmt: skip


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
                 "1 = clean behaviour restored, 0 = corrupt behaviour")  # fmt: skip


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
    return _view(lm, f"Attribution patching: {answer!r} vs {foil!r}", z, corrupt, note)

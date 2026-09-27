"""Sparse autoencoder features on the residual stream, with SAELens SAEs (the sae extra).

Load the SAE with SAELens: `SAE.from_pretrained(release, sae_id)` or `SAE.load_from_disk(path)`.
loupe reads the residual at the SAE's hook with nnsight, so the model stays the unmodified HF one,
and saves a feature's decoder row as a direction, so Steer and Ablate work on features unchanged.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import positions
from loupe.analysis.project import top_examples
from loupe.analysis.views import heatmap, table
from loupe.core import Direction
from loupe.interventions.specs import EMBED, Plan
from loupe.models import blocks
from loupe.vectors import save_vector

if TYPE_CHECKING:
    from sae_lens import SAE

_HOOK = re.compile(r"^blocks\.(\d+)\.hook_resid_(pre|post)$")


def neuronpedia(sae: SAE, feature: int) -> str | None:
    """The feature's Neuronpedia dashboard, for SAEs SAELens knows a Neuronpedia id for; on
    LOUPE_NEURONPEDIA's origin when set, for a self-hosted Neuronpedia."""
    origin = os.environ.get("LOUPE_NEURONPEDIA", "https://neuronpedia.org").rstrip("/")
    sae_id = sae.cfg.metadata.neuronpedia_id
    return f"{origin}/{sae_id}/{feature}" if sae_id else None


def _layer(sae: SAE) -> int:
    """The block whose output the SAE reads: resid_post L is block L, resid_pre L is block L - 1.

    -1 is the embeddings (resid_pre 0), the same key Steer and Ablate use for them.
    """
    hook = str(sae.cfg.metadata.hook_name)
    match = _HOOK.match(hook)
    if not match:
        raise ValueError(f"SAE hook {hook!r} is not a residual stream hook (blocks.L.hook_resid_*)")
    layer = int(match.group(1))
    return layer if match.group(2) == "post" else layer - 1


@torch.no_grad()
def sae_features(
    lm: LanguageModel, sae: SAE, prompt: str, k: int = 5
) -> tuple[torch.Tensor, dict[str, Any], dict[str, Any]]:
    """Encode a prompt's residual at the SAE's layer: activations [positions, features], a table
    of each token's top-k features, and a heatmap of the k features that peak highest, by position.
    """
    layer = _layer(sae)
    with lm.trace(prompt):
        site = blocks(lm)[0].input if layer == EMBED else blocks(lm)[layer].output
        resid = site[0].save()
    acts = sae.encode(resid.to(sae.W_dec)).float().cpu()
    labels = positions(lm, prompt)
    top = acts.topk(k, dim=-1)
    rows: list[list[Any]] = []
    links: list[list[str | None]] = []
    for pos, (values, indices) in enumerate(zip(top.values, top.indices, strict=True)):
        active = [(int(i), float(v)) for v, i in zip(values, indices, strict=True) if v > 0]
        pad = [None] * (k - len(active))
        rows.append(
            [pos, labels[pos].split(":", 1)[1], *[f"#{i} {v:.2f}" for i, v in active], *pad]
        )
        links.append([None, None, *[neuronpedia(sae, i) for i, _ in active], *pad])
    hook = sae.cfg.metadata.hook_name
    columns = ["position", "token", *[f"top {j + 1}" for j in range(k)]]
    note = "feature index and activation; empty where fewer are active"
    has_links = sae.cfg.metadata.neuronpedia_id is not None
    if has_links:
        note += "; a feature opens its Neuronpedia dashboard"
    view_table = table(f"SAE features per token at {hook}", columns, rows, note=note,
                       links=links if has_links else None,
                       embed="neuronpedia" if has_links else None)  # fmt: skip
    peak = acts.max(0).values.topk(min(k, acts.shape[1])).indices.tolist()
    view_heat = heatmap(f"Top SAE features over positions at {hook}",
                        [acts[:, f].tolist() for f in peak], x=labels, y=[f"#{f}" for f in peak],
                        x_label="position", y_label="feature")  # fmt: skip
    return acts, view_table, view_heat


@torch.no_grad()
def feature_examples(
    lm: LanguageModel,
    sae: SAE,
    feature: int,
    prompts: list[str],
    k: int = 10,
    plan: Plan | None = None,
) -> tuple[torch.Tensor, dict[str, Any]]:
    """A local dashboard for one feature: its peak per prompt and the k texts it fires on most."""

    def score(h: torch.Tensor) -> torch.Tensor:
        return sae.encode(h.to(sae.W_dec))[..., feature]

    title = f"Feature #{feature} at {sae.cfg.metadata.hook_name}: top examples"
    return top_examples(lm, prompts, _layer(sae), score, title, k, plan)


def save_feature(
    sae: SAE, feature: int, name: str, model: str, run: str | None = None
) -> Direction:
    """Save a feature's decoder row as a direction at the SAE's layer, to steer or ablate."""
    notes = f"feature {feature} of the SAE at {sae.cfg.metadata.hook_name}"
    if url := neuronpedia(sae, feature):
        notes += f"; {url}"
    return save_vector(name, sae.W_dec[feature], model=model, layer=_layer(sae),
                       method="sae-decoder", run=run, notes=notes)  # fmt: skip

"""Sparse autoencoder features on the residual stream, with SAELens SAEs (the sae extra).

Load the SAE with SAELens: `SAE.from_pretrained(release, sae_id)` or `SAE.load_from_disk(path)`.
loupe reads the residual at the SAE's hook with nnsight, so the model stays the unmodified HF one,
and saves a feature's decoder row as a direction, so Steer and Ablate work on features unchanged.

feature_dashboards is the local feature dashboard for any SAE, on any dataset: how often a feature
fires and how strongly (density, a histogram), the texts it fires on most with its activation on
every token, and the tokens its decoder direction promotes and suppresses through the unembedding.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import positions, token_strings
from loupe.analysis.project import shared_ends, top_examples
from loupe.analysis.views import heatmap, table, token_row, tokens
from loupe.core import Direction
from loupe.interventions.specs import EMBED, Plan
from loupe.models import blocks
from loupe.vectors import save_vector

if TYPE_CHECKING:
    from sae_lens import SAE

_HOOK = re.compile(r"^blocks\.(\d+)\.hook_resid_(pre|post)$")


def neuronpedia_origin() -> str:
    """LOUPE_NEURONPEDIA when set (a self-hosted Neuronpedia), else the public one."""
    return os.environ.get("LOUPE_NEURONPEDIA", "https://neuronpedia.org").rstrip("/")


def neuronpedia(sae: SAE, feature: int) -> str | None:
    """The feature's Neuronpedia dashboard, for SAEs SAELens knows a Neuronpedia id for."""
    sae_id = sae.cfg.metadata.neuronpedia_id
    return f"{neuronpedia_origin()}/{sae_id}/{feature}" if sae_id else None


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


def _encode(lm: LanguageModel, sae: SAE, chunk: list[str], layer: int) -> torch.Tensor:
    """The SAE's features of a batch's residual at its layer: [batch, positions, features]."""
    with lm.trace(chunk):
        site = blocks(lm)[0].input if layer == EMBED else blocks(lm)[layer].output
        h = site.save()
    return sae.encode(h.to(sae.W_dec)).float()


@torch.no_grad()
def feature_dashboards(
    lm: LanguageModel,
    sae: SAE,
    prompts: list[str],
    features: list[int] | None = None,
    top_n: int = 24,
    k: int = 8,
    bins: int = 24,
    logits: int = 10,
    batch_size: int = 8,
    before: int = 32,
    after: int = 8,
) -> list[dict[str, Any]]:
    """One dashboard per feature: the given features, else the top_n that peak highest on the
    prompts among those firing on at least two of them.

    Density is the share of tokens a feature fires on (activation above zero); the histogram is of
    its nonzero activations; examples are its k top texts, the before and after tokens around each
    peak, with the activation at every token; the
    promoted and suppressed tokens are the unembedding's rows most aligned with the feature's
    decoder direction, as Neuronpedia's logit tables read it (no final norm). The first token of
    every prompt (a BOS token, or where a model without one puts its huge-norm attention sink) and
    the tokens every prompt starts and ends with (a chat template) are left out of every measure.
    """
    layer = _layer(sae)
    ids = [lm.tokenizer(p)["input_ids"] for p in prompts]
    head, tail = shared_ends(ids)
    batches = [prompts[i : i + batch_size] for i in range(0, len(prompts), batch_size)]

    def real(chunk: list[str]) -> torch.Tensor:
        mask = lm.tokenizer(chunk, return_tensors="pt", padding=True)["attention_mask"].bool()
        for row in mask:  # padding is on the left; drop the shared ends of the real tokens
            where = row.nonzero().flatten()
            row[where[: max(head, 1)]] = False
            row[where[len(where) - tail :]] = False
        return mask

    # pass 1: every feature's peak per prompt, how many tokens it fires on, its maximum
    peaks, fired, total = [], torch.zeros(sae.W_dec.shape[0]), 0
    for chunk in batches:
        acts, mask = _encode(lm, sae, chunk, layer).cpu(), real(chunk)
        acts[~mask] = 0.0
        peaks.append(acts.amax(1))
        fired += (acts > 0).sum((0, 1)).float()
        total += int(mask.sum())
    peak = torch.cat(peaks)  # [prompts, features]
    if features is None:
        live = ((peak > 0).sum(0) >= min(2, len(prompts))).nonzero().flatten()
        order = peak[:, live].amax(0).argsort(descending=True)
        features = live[order][:top_n].tolist()
    chosen = torch.tensor(features, dtype=torch.long)
    tops = {f: peak[:, f].topk(min(k, len(prompts))).indices.tolist() for f in features}
    wanted = {i for idx in tops.values() for i in idx}

    # pass 2: the chosen features' activations, all nonzero values and the top texts' tokens
    values: dict[int, list[torch.Tensor]] = {f: [] for f in features}
    per_token: dict[int, torch.Tensor] = {}
    for b, chunk in enumerate(batches):
        acts = _encode(lm, sae, chunk, layer)[..., chosen.to(sae.W_dec.device)].cpu()
        mask = real(chunk)
        acts[~mask] = 0.0  # the left-out tokens show as zero in the examples too
        full = lm.tokenizer(chunk, return_tensors="pt", padding=True)["attention_mask"].bool()
        for j, f in enumerate(features):
            got = acts[..., j][mask]
            values[f].append(got[got > 0])
        for r in range(len(chunk)):
            if b * batch_size + r in wanted:
                per_token[b * batch_size + r] = acts[r][full[r]]  # [real tokens, chosen]

    hf: Any = lm._model
    unembed = hf.get_output_embeddings().weight.float()  # [vocab, hidden]
    hook = str(sae.cfg.metadata.hook_name)
    out = []
    for j, f in enumerate(features):
        nonzero = torch.cat(values[f])
        top = float(nonzero.max()) if len(nonzero) else 0.0
        counts = torch.histc(nonzero, bins=bins, min=0.0, max=top) if top > 0 else torch.zeros(bins)
        effect = unembed @ sae.W_dec[f].float().to(unembed.device)
        up, down = effect.topk(logits), (-effect).topk(logits)

        def decode(ids: list[int]) -> list[str]:
            return [str(lm.tokenizer.decode([i])) for i in ids]

        rows = []
        for i in tops[f]:
            if peak[i, f] <= 0:
                continue
            act = per_token[i][:, j]
            at = int(act.argmax())  # a window around the peak, as a dashboard reads
            lo, hi = max(0, at - before), at + after + 1
            series = {"activation": act[lo:hi].round(decimals=4).tolist()}
            text = token_strings(lm, prompts[i])[lo:hi]
            rows.append(token_row(text, series, f"peak {peak[i, f]:.3f}"))
        out.append({
            "feature": f, "hook": hook, "layer": layer,
            "density": float(fired[f] / max(total, 1)), "max": top,
            "histogram": {"edges": torch.linspace(0, top, bins + 1).tolist(),
                          "counts": counts.int().tolist()},
            "promoted": list(map(list, zip(decode(up.indices.tolist()), up.values.tolist(),
                                           strict=True))),
            "suppressed": list(map(list, zip(decode(down.indices.tolist()),
                                             (-down.values).tolist(), strict=True))),
            "examples": tokens(f"Feature #{f}: top examples", rows,
                               f"top {len(rows)} of {len(prompts)} texts by peak activation"),
            "neuronpedia": neuronpedia(sae, f),
        })  # fmt: skip
    return out

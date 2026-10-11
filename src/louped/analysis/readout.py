"""One prompt read layer by layer, for Probe's Inspect: what each layer would predict (the logit
lens, with its top tokens, entropy and distance from the final answer), where one target token's
probability and rank rise, which layer's attention and MLP and which head write that token (direct
logit attribution), and what each head does (entropy, previous-token and first-token attention).

Direct logit attribution freezes the final norm at the last layer's scale, so each part's
contribution is linear. The norm is read as a scale and a gain checked against the norm's own
output, not guessed from its class. What the parts do not explain (the norm's and the head's
biases) is returned as its own term, so the parts and it add up to the target's logit before any
softcap. On blocks that norm their attention's output before adding it (Gemma 2 and 3, OLMo 2),
attention's write is that normed output, and each head's share goes through that norm frozen at
its scale.
"""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from louped.analysis.activations import token_strings
from louped.interventions import EMBED, Plan, apply_at, apply_heads
from louped.models import attention, blocks, final_norm, n_heads, out_proj

#: Top tokens kept for each layer and position.
TOP = 5
#: Per-head attribution is layers x heads x positions; above this, only the last position's.
MAX_HEAD_CELLS = 200_000
#: How far a norm read as scale and gain may be from the norm's own output, relative to it.
NORM_TOLERANCE = 0.05


def _r(t: torch.Tensor, digits: int = 4) -> Any:
    return t.round(decimals=digits).tolist()


class Linear:
    """A norm at one input, as a linear map: x -> (x - mean if centred) * gain / scale + bias."""

    def __init__(self, scale: torch.Tensor, gain: torch.Tensor, centred: bool, bias: torch.Tensor):
        self.scale, self.gain, self.centred, self.bias = scale, gain, centred, bias

    def read(self, direction: torch.Tensor) -> torch.Tensor:
        """The vector whose dot product with a part, divided by scale, is the part's share."""
        v = direction * self.gain
        return v - v.mean() if self.centred else v


def _linear(norm: torch.nn.Module, x: torch.Tensor) -> Linear:
    """A norm (RMSNorm, LayerNorm, Gemma's 1 + weight) frozen at its scale on x [positions, hidden],
    checked against its own output there; ValueError naming the norm when no reading matches."""
    param = next(norm.parameters(), None)
    out = norm(x.to(param) if param is not None else x).float().cpu()
    weight = getattr(norm, "weight", None)
    w = torch.ones(x.shape[-1]) if weight is None else weight.detach().float().cpu()
    b = getattr(norm, "bias", None)
    bias = torch.zeros(x.shape[-1]) if b is None else b.detach().float().cpu()
    eps = float(getattr(norm, "eps", None) or getattr(norm, "variance_epsilon", None) or 1e-6)
    best: tuple[float, Linear] | None = None
    for centred in (False, True):
        c = x - x.mean(-1, keepdim=True) if centred else x
        scale = (c.pow(2).mean(-1) + eps).sqrt()
        for gain in (w, 1 + w):
            err = float((c * gain / scale[:, None] + bias - out).norm() / (out.norm() + 1e-12))
            if best is None or err < best[0]:
                best = (err, Linear(scale, gain, centred, bias))
    assert best is not None
    if best[0] > NORM_TOLERANCE:
        raise ValueError(f"{type(norm).__name__} is not a scale and a gain louped can read "
                         f"(off by {best[0]:.0%}); direct logit attribution needs one")  # fmt: skip
    return best[1]


def _token(lm: LanguageModel, target: str | int | None, fallback: int) -> int:
    """A token id: target's, when it is an id or one token's text; else fallback."""
    if target is None or target == "":
        return fallback
    if isinstance(target, int):
        if not 0 <= target < len(lm.tokenizer):
            raise ValueError(f"token {target} is not in the vocabulary")
        return target
    ids = lm.tokenizer(target, add_special_tokens=False)["input_ids"]
    if len(ids) != 1:
        raise ValueError(f"{target!r} is {len(ids)} tokens; the target is one token")
    return int(ids[0])


@torch.no_grad()
def readout(
    lm: LanguageModel,
    prompt: str,
    plan: Plan | None = None,
    target: str | int | None = None,
    pattern: torch.Tensor | None = None,
) -> dict[str, Any]:
    """The prompt read at every layer and position, in the fields of
    louped.server.playground.Readout, which says what each holds. target: the token to follow, an
    id or one token's text; by default the model's prediction at the last position. pattern:
    attention weights [layers, heads, query, key] (louped.analysis.attention_patterns), for the
    heads' scores."""
    layers = blocks(lm)
    heads = n_heads(lm)
    # a block that norms its attention's output before adding it to the residual
    post = [hasattr(b._module, "post_feedforward_layernorm") for b in layers]
    saved_in: list[Any] = []
    saved_attn: list[Any] = []
    saved_write: list[Any] = []
    saved_out: list[Any] = []
    with lm.trace(prompt):
        apply_at(lm, plan, EMBED)
        emb = layers[0].input[0].save()
        for i, layer in enumerate(layers):
            apply_heads(lm, plan, i)
            attn = attention(layer)
            saved_in.append(out_proj(attn).input.save())
            saved_attn.append(attn.output[0].save())
            if post[i]:
                saved_write.append(layer.post_attention_layernorm.output.save())
            apply_at(lm, plan, i, heads=False)  # the heads were edited above
            saved_out.append(layer.output[0].save())
    # each block's output is the residual [positions, hidden], as in louped.analysis.resid
    stream = torch.stack([emb.float().cpu(), *(o.float().cpu() for o in saved_out)])
    norm, head = final_norm(lm)._module, lm.lm_head._module
    param = next(head.parameters())
    cap = getattr(lm._model.config, "final_logit_softcapping", None)

    def lens(h: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """A residual's logits before the softcap, and its log-probabilities, on the device."""
        raw = head(norm(h.to(param))).float()
        return raw, (torch.tanh(raw / cap) * cap if cap else raw).log_softmax(-1)

    # one layer at a time: [layers, positions, vocabulary] would not fit for a large vocabulary
    raw_final, final = lens(stream[-1])
    tid = _token(lm, target, int(final[-1].argmax()))
    rows: dict[str, list[torch.Tensor]] = {k: [] for k in ("ids", "probs", "tp", "rank", "ent",
                                                            "kl")}  # fmt: skip
    for h in stream:
        _, logp = lens(h)
        probs = logp.exp()
        top = probs.topk(TOP, dim=-1)
        tp = probs[:, tid]
        rows["ids"].append(top.indices.cpu())
        rows["probs"].append(top.values.cpu())
        rows["tp"].append(tp.cpu())
        rows["rank"].append((probs > tp[:, None]).sum(-1).cpu())
        rows["ent"].append((-(probs * logp).sum(-1)).cpu())
        rows["kl"].append((final.exp() * (final - logp)).sum(-1).cpu())
        del logp, probs
    grid = {k: torch.stack(v) for k, v in rows.items()}
    target_logit = raw_final[:, tid].cpu()

    # direct logit attribution through the frozen final norm
    frozen = _linear(norm, stream[-1])
    direction = frozen.read(head.weight.detach().float().cpu()[tid])

    def dla(x: torch.Tensor) -> torch.Tensor:
        return (x @ direction) / frozen.scale

    t = stream.shape[1]
    writes = iter(saved_write)
    attn_out: list[torch.Tensor] = []
    per_head: list[Any] = []
    positions = list(range(t)) if len(layers) * heads * t <= MAX_HEAD_CELLS else [t - 1]
    for i in range(len(layers)):
        raw = saved_attn[i].float().cpu().reshape(t, -1)
        proj = out_proj(attention(layers[i]))._module
        w_o = proj.weight.detach().float().cpu()
        if type(proj).__name__ == "Conv1D":  # GPT-2 keeps its projection as [in, out]
            w_o = w_o.T
        read, scale = direction, frozen.scale
        if post[i]:
            attn_out.append(next(writes).float().cpu().reshape(t, -1))
            through = _linear(layers[i].post_attention_layernorm._module, raw)
            read, scale = through.read(direction), frozen.scale * through.scale
        else:
            attn_out.append(raw)
        per = (w_o.T @ read).reshape(heads, -1)  # [heads, head_dim]
        x = saved_in[i].float().cpu().reshape(t, heads, -1)[positions]  # [P, heads, head_dim]
        per_head.append(_r(((x * per).sum(-1) / scale[positions, None]).T, 3))
    attn = torch.stack(attn_out)
    mlp = stream[1:] - stream[:-1] - attn
    parts = dla(stream[0]) + sum(dla(a) for a in attn) + sum(dla(m) for m in mlp)

    if pattern is not None:
        p = pattern.float()
        q = p.shape[-1]
        head_entropy = -(p * (p + 1e-12).log()).sum(-1).mean(-1)
        if q > 1:
            idx = torch.arange(1, q)
            head_prev = p[:, :, idx, idx - 1].mean(-1)
            head_first = p[:, :, 1:, 0].mean(-1)
        else:
            head_prev = head_first = torch.zeros(p.shape[:2])
    else:
        head_entropy = head_prev = head_first = torch.zeros(len(layers), heads)

    named = {int(i) for i in grid["ids"].flatten().tolist()} | {tid}
    return dict(
        tokens=token_strings(lm, prompt),
        layers=["emb", *(str(i) for i in range(len(layers)))],
        vocab={i: str(lm.tokenizer.decode([i])) for i in sorted(named)},
        top_ids=grid["ids"].tolist(),
        top_probs=_r(grid["probs"]),
        entropy=_r(grid["ent"], 3),
        kl=_r(grid["kl"].clamp(min=0), 3),
        target=tid,
        target_prob=_r(grid["tp"], 5),
        target_rank=grid["rank"].tolist(),
        target_logit=_r(target_logit, 3),
        softcap=cap,
        dla_embed=_r(dla(stream[0]), 3),
        dla_attn=_r(torch.stack([dla(a) for a in attn]), 3),
        dla_mlp=_r(torch.stack([dla(m) for m in mlp]), 3),
        dla_rest=_r(target_logit - parts, 3),
        dla_heads=per_head,
        head_positions=positions,
        head_entropy=_r(head_entropy, 3),
        head_prev=_r(head_prev, 3),
        head_first=_r(head_first, 3),
    )

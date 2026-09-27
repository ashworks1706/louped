"""Masked diffusion language models (LLaDA, Dream, any Hugging Face masked LM) and their sampler.

A masked diffusion model does not write left to right. Generation starts from a fully masked reply;
each step predicts every masked position and commits the most confident, block by block from the
left (LLaDA's low-confidence remasking). on_step(step, steps) runs before every step, which is where
a phase schedule changes the live adapters along the trajectory. No prefix cache is kept, so the
adapters may change at any step. Dream predicts the next position, so its logits are shifted by one.

The training objective is here too: a random fraction t of the reply is masked, the prompt never,
and the cross entropy on the masked tokens is weighted by 1/t.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import torch
import torch.nn.functional as F

from loupe.core import saved_model

#: Model types whose code lives on the Hub rather than in transformers.
REMOTE = {"llada": 126336, "dream": None}


@dataclass
class Diffusion:
    """A masked diffusion model with what its sampler needs."""

    model: Any
    tokenizer: Any
    mask_id: int
    shift: bool


def base(name: str, dtype: torch.dtype | str = "auto", device: str | None = None) -> Any:
    """The bare HF model saved under <home>/models by name, or a Hub id or path."""
    from transformers import AutoConfig, AutoModel, AutoModelForMaskedLM

    path = str(saved_model(name) or name)
    kind = AutoConfig.from_pretrained(path, trust_remote_code=True).model_type.lower()
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    if kind in REMOTE:
        return AutoModel.from_pretrained(path, dtype=dtype, trust_remote_code=True).to(device)
    return AutoModelForMaskedLM.from_pretrained(path, dtype=dtype).to(device)


def load_diffusion(
    name: str,
    bank: list[str] | None = None,
    merges: list[dict[str, Any]] | None = None,
    dtype: torch.dtype | str = "auto",
    device: str | None = None,
) -> Diffusion:
    """A masked diffusion model by name, with an adapter bank as loupe.models.load takes one."""
    from loupe.models.adapters import activate, merge
    from loupe.models.adapters import bank as build_bank
    from loupe.models.load import tokenizer

    model = base(name, dtype, device)
    tok = tokenizer(str(saved_model(name) or name))
    if bank:
        peft = build_bank(model, bank)
        for spec in merges or []:
            merge(peft, **spec)
        activate(peft, [])
        model = peft
    return Diffusion(model.eval(), tok, *load_mask(model, tok))


def load_mask(model: Any, tok: Any) -> tuple[int, bool]:
    """The model's mask token id, and whether its logits predict the next position (Dream)."""
    kind = model.config.model_type.lower()
    mask = REMOTE.get(kind) or tok.mask_token_id
    if mask is None:
        raise ValueError(f"{kind}: the tokenizer has no mask token")
    return int(mask), kind == "dream"


def logits(d: Diffusion, x: torch.Tensor) -> torch.Tensor:
    """Predictions for every position of x, aligned to it."""
    out = d.model(input_ids=x)
    z = out.logits if hasattr(out, "logits") else out
    return torch.cat([z[:, :1], z[:, :-1]], dim=1) if d.shift else z


def transfers(masked: int, steps: int) -> list[int]:
    """How many positions each step commits: an even split, the remainder to the first steps."""
    per, extra = divmod(masked, steps)
    return [per + (1 if i < extra else 0) for i in range(steps)]


@torch.no_grad()
def denoise(
    d: Diffusion,
    prompt: torch.Tensor,
    length: int = 64,
    block: int | None = None,
    steps: int | None = None,
    temperature: float = 0.0,
    on_step: Callable[[int, int], None] | None = None,
) -> torch.Tensor:
    """The prompt ids [batch, p] followed by length generated ids."""
    block = block or length
    steps = steps or length
    if length % block or steps % (length // block):
        raise ValueError("length must be whole blocks and steps a multiple of the block count")
    n_blocks, batch, p = length // block, prompt.shape[0], prompt.shape[1]
    x = torch.full((batch, p + length), d.mask_id, dtype=torch.long, device=prompt.device)
    x[:, :p] = prompt
    step = 0
    for b in range(n_blocks):
        s0, s1 = p + b * block, p + (b + 1) * block
        for k in transfers(block, steps // n_blocks):
            if on_step is not None:
                on_step(step, steps)
            step += 1
            masked = x[:, s0:s1] == d.mask_id
            z = logits(d, x)[:, s0:s1].float()
            z[..., d.mask_id] = float("-inf")
            if temperature > 0:
                pred = torch.multinomial(F.softmax(z / temperature, -1).flatten(0, 1), 1)
                pred = pred.view(batch, -1)
            else:
                pred = z.argmax(-1)
            conf = F.softmax(z, -1).gather(-1, pred.unsqueeze(-1)).squeeze(-1)
            conf = torch.where(masked, conf, float("-inf"))
            commit = torch.zeros_like(masked).scatter_(1, conf.topk(k, dim=1).indices, True)
            x[:, s0:s1] = torch.where(commit & masked, pred, x[:, s0:s1])
    return x


def generate(
    d: Diffusion, prompts: list[str], on_step: Callable[[int, int], None] | None = None, **sampler
) -> list[str]:
    """Each prompt's reply, cut at the first end of sequence. sampler is denoise's arguments."""
    out = []
    eos = d.tokenizer.eos_token_id
    device = next(d.model.parameters()).device
    for text in prompts:
        ids = d.tokenizer(text, return_tensors="pt", add_special_tokens=False)["input_ids"]
        reply = denoise(d, ids.to(device), on_step=on_step, **sampler)[0, ids.shape[1] :].tolist()
        if eos in reply:
            reply = reply[: reply.index(eos)]
        out.append(d.tokenizer.decode(reply, skip_special_tokens=True).strip())
    return out


def loss(d: Diffusion, ids: torch.Tensor, prompt_len: torch.Tensor, eps: float = 1e-3):
    """The masked diffusion SFT loss on [batch, n] ids whose first prompt_len[i] are the prompt."""
    batch, n = ids.shape
    t = torch.rand(batch, 1, device=ids.device)
    p_mask = (1 - eps) * t + eps
    reply = torch.arange(n, device=ids.device)[None] >= prompt_len[:, None]
    masked = (torch.rand(batch, n, device=ids.device) < p_mask) & reply
    z = logits(d, torch.where(masked, d.mask_id, ids))
    ce = F.cross_entropy(z[masked].float(), ids[masked], reduction="none")
    lengths = reply.sum(1, keepdim=True).expand(-1, n)[masked]
    return (ce / p_mask.expand(-1, n)[masked] / lengths).sum() / batch

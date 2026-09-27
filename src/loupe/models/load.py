"""One loader for every Hugging Face causal LM, and where each family keeps its decoder blocks.

nnsight wraps the unmodified HF model, so numerics are the model's own. The only per-family
knowledge loupe needs is the path to the list of decoder blocks, whose outputs are the residual
stream every intervention and analysis reads or writes.
"""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel
from transformers import PreTrainedTokenizerFast

from loupe.core import home

#: Attribute paths to the decoder blocks, tried in order. Covers Qwen2/3, Llama, Mistral, Gemma,
#: Phi (model.layers), GPT-2 (transformer.h) and GPT-NeoX/Pythia (gpt_neox.layers).
BLOCK_PATHS = ("model.layers", "transformer.h", "gpt_neox.layers")


def load(
    model: str | Any,
    *,
    tokenizer: Any = None,
    dtype: torch.dtype | str = "auto",
    device: str | None = None,
) -> LanguageModel:
    """A model saved under <home>/models by name, a Hub id or path, or a built HF model.

    Padding is set to the left so the last position of every row is its last real token, which is
    what generation needs and what last-token analyses read.
    """
    if isinstance(model, str):
        local = home() / "models" / model
        kwargs: dict[str, Any] = {}
        if (local / "config.json").exists():
            model = str(local)
            if (local / "tokenizer.json").exists():
                # What was saved, exactly: AutoTokenizer would rebuild the family's default
                # tokenizer from model_type and drop a custom pre-tokenizer or decoder.
                kwargs["tokenizer"] = PreTrainedTokenizerFast.from_pretrained(model)
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        lm = LanguageModel(model, device_map=device, dtype=dtype, dispatch=True, **kwargs)
    else:
        lm = LanguageModel(model, tokenizer=tokenizer)
    lm.tokenizer.padding_side = "left"
    if lm.tokenizer.pad_token is None:
        lm.tokenizer.pad_token = lm.tokenizer.eos_token
    return lm


def _resolve(root: Any, path: str) -> Any:
    for part in path.split("."):
        root = getattr(root, part)
    return root


def blocks(lm: LanguageModel) -> Any:
    """The decoder blocks, as nnsight envoys; block i's output is the residual after layer i."""
    for path in BLOCK_PATHS:
        try:
            return _resolve(lm, path)
        except AttributeError:
            continue
    raise ValueError(f"no decoder blocks at any of {BLOCK_PATHS}; add this family's path")


def n_layers(lm: LanguageModel) -> int:
    return len(blocks(lm))


def chat(lm: LanguageModel, user: str, system: str | None = None) -> str:
    """A user turn rendered with the model's own chat template, ready for the assistant's reply."""
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user}
    ]
    text = lm.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return str(text)

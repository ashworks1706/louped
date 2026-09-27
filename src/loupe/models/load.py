"""One loader for every Hugging Face causal LM, and where each family keeps its decoder blocks.

nnsight wraps the unmodified HF model, so numerics are the model's own. The only per-family
knowledge loupe needs is where the decoder blocks are, whose outputs are the residual stream every
intervention and analysis reads or writes, and where the final norm is, for the logit lens.
"""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel
from transformers import PreTrainedTokenizerFast

from loupe.core import saved_model

#: Attribute paths to the decoder blocks, tried in order. Covers Qwen2/3, Llama, Mistral, Gemma,
#: Phi (model.layers), GPT-2 (transformer.h) and GPT-NeoX/Pythia (gpt_neox.layers).
BLOCK_PATHS = ("model.layers", "transformer.h", "gpt_neox.layers")
NORM_PATHS = ("model.norm", "transformer.ln_f", "gpt_neox.final_layer_norm")


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
        local = saved_model(model)
        kwargs: dict[str, Any] = {}
        if local is not None:
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


def _first(lm: LanguageModel, paths: tuple[str, ...]) -> Any:
    for path in paths:
        root: Any = lm
        try:
            for part in path.split("."):
                root = getattr(root, part)
        except AttributeError:
            continue
        return root
    raise ValueError(f"nothing at any of {paths}; add this family's path")


def blocks(lm: LanguageModel) -> Any:
    """The decoder blocks, as nnsight envoys; block i's output is the residual after layer i."""
    return _first(lm, BLOCK_PATHS)


def final_norm(lm: LanguageModel) -> Any:
    """The norm applied to the last residual before the unembedding, as an nnsight envoy."""
    return _first(lm, NORM_PATHS)


def n_layers(lm: LanguageModel) -> int:
    return len(blocks(lm))


def chat(lm: LanguageModel, user: str, system: str | None = None) -> str:
    """A user turn rendered with the model's own chat template, ready for the assistant's reply."""
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user}
    ]
    text = lm.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return str(text)

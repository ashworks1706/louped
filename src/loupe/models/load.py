"""One loader for every Hugging Face causal LM, and where each family keeps its decoder blocks.

nnsight wraps the unmodified HF model, so numerics are the model's own. The only per-family
knowledge loupe needs is where the decoder blocks are, whose outputs are the residual stream every
intervention and analysis reads or writes, where the final norm is, for the logit lens, and where
each block's attention is, for its weights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from nnsight import LanguageModel
from transformers import AutoTokenizer, PreTrainedTokenizerFast

from loupe.core import saved_model

#: Attribute paths to the decoder blocks, tried in order. Covers Qwen2/3, Llama, Mistral, Gemma,
#: Phi (model.layers), GPT-2 (transformer.h) and GPT-NeoX/Pythia (gpt_neox.layers).
BLOCK_PATHS = ("model.layers", "transformer.h", "gpt_neox.layers")
NORM_PATHS = ("model.norm", "transformer.ln_f", "gpt_neox.final_layer_norm")
#: A block's attention module, whose output[1] is the attention weights under eager attention.
ATTN_PATHS = ("self_attn", "attn", "attention")


def load(
    model: str | Any,
    *,
    tokenizer: Any = None,
    dtype: torch.dtype | str = "auto",
    device: str | None = None,
    adapter: str | Path | None = None,
    bank: list[str] | None = None,
    merges: list[dict[str, Any]] | None = None,
) -> LanguageModel:
    """A model saved under <home>/models by name, a Hub id or path, or a built HF model. With an
    adapter (a LoRA directory, such as a training checkpoint), merged into the named model. With a
    bank, those named adapters loaded unmerged and inactive (loupe.models.adapters.activate), plus
    each of merges ({"names": [...], "method": "ties", ...}) added as a merged adapter.

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
        if adapter is not None or bank:
            tok = kwargs.get("tokenizer") or AutoTokenizer.from_pretrained(model)
            built = (
                _merged(model, adapter, dtype, device)
                if adapter
                else _banked(model, bank or [], merges or [], dtype, device)
            )
            lm = LanguageModel(built, tokenizer=tok)
        else:
            lm = LanguageModel(model, device_map=device, dtype=dtype, dispatch=True, **kwargs)
    else:
        lm = LanguageModel(model, tokenizer=tokenizer)
    lm.tokenizer.padding_side = "left"
    if lm.tokenizer.pad_token is None:
        lm.tokenizer.pad_token = lm.tokenizer.eos_token
    return lm


def tokenizer(path: str) -> Any:
    """A saved tokenizer exactly as saved (AutoTokenizer would rebuild the family's default from
    model_type and drop a custom pre-tokenizer or decoder), else the Hub's."""
    if Path(path, "tokenizer.json").exists():
        return PreTrainedTokenizerFast.from_pretrained(path)
    return AutoTokenizer.from_pretrained(path)


def _merged(model: str, adapter: str | Path, dtype: torch.dtype | str, device: str) -> Any:
    try:
        from peft import PeftModel
    except ImportError as exc:
        raise ImportError("loading an adapter needs the train extra: loupelab[train]") from exc
    from transformers import AutoModelForCausalLM

    base = AutoModelForCausalLM.from_pretrained(model, dtype=dtype, device_map=device)
    return PeftModel.from_pretrained(base, str(adapter)).merge_and_unload()


def _banked(
    model: str,
    names: list[str],
    merges: list[dict[str, Any]],
    dtype: torch.dtype | str,
    device: str,
) -> Any:
    from transformers import AutoModelForCausalLM

    from loupe.models.adapters import activate, bank, merge

    base = AutoModelForCausalLM.from_pretrained(model, dtype=dtype, device_map=device)
    peft = bank(base, names)
    for spec in merges:
        merge(peft, **spec)
    activate(peft, [])
    return peft.base_model.model  # the HF model, its LoRA layers injected in place


def _first(obj: Any, paths: tuple[str, ...]) -> Any:
    for path in paths:
        root: Any = obj
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


def attention(block: Any) -> Any:
    """A decoder block's attention module, as an nnsight envoy."""
    return _first(block, ATTN_PATHS)


def n_layers(lm: LanguageModel) -> int:
    return len(blocks(lm))


def chat(lm: LanguageModel, user: str, system: str | None = None) -> str:
    """A user turn rendered with the model's own chat template, ready for the assistant's reply.

    Thinking is off for templates that have it (Qwen3), so replies start with the answer.
    """
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user}
    ]
    text = lm.tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    return str(text)

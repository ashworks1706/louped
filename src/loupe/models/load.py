"""One loader for every Hugging Face causal LM, and where each family keeps its decoder blocks.

nnsight wraps the unmodified HF model, so numerics are the model's own. The only per-family
knowledge loupe needs is where the decoder blocks are, whose outputs are the residual stream every
intervention and analysis reads or writes, where the final norm is, for the logit lens, and where
each block's attention is, for its weights, and its output projection, for per-head edits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# anyio rejects a TypedAttributeSet class defined after nnsight mounts save on every object.
import anyio._backends._asyncio
import anyio.streams.file
import anyio.streams.tls  # noqa: F401
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
#: An attention module's output projection, whose input is the heads' outputs side by side.
OUT_PATHS = ("o_proj", "out_proj", "c_proj", "dense")


def load(
    model: str | Any,
    *,
    tokenizer: Any = None,
    dtype: torch.dtype | str = "auto",
    device: str | None = None,
    adapter: str | Path | None = None,
    bank: list[str] | None = None,
    merges: list[dict[str, Any]] | None = None,
    revision: str | None = None,
    attn: str | None = None,
) -> LanguageModel:
    """A model saved under <home>/models by name, a Hub id or path, or a built HF model; a Hub id
    at revision (a commit, branch or tag) when one is given. With an adapter (a LoRA directory,
    such as a training checkpoint), merged into the named model. With a bank, those named adapters
    loaded unmerged and inactive (loupe.models.adapters.activate), plus each of merges
    ({"names": [...], "method": "ties", ...}) added as a merged adapter.

    attn picks the attention kernel (attn_implementation): eager, sdpa, flash_attention_2,
    flex_attention, a name registered with transformers' AttentionInterface, or file.py:function to
    register that function first (attention_kernel). Only eager returns attention weights; the
    attention views switch to it for their own trace, and head edits work under any kernel.

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
        hf: dict[str, Any] = {"dtype": dtype, "device_map": device, "revision": revision}
        if attn:
            hf["attn_implementation"] = attention_kernel(attn)
        if adapter is not None or bank:
            tok = kwargs.get("tokenizer") or AutoTokenizer.from_pretrained(model, revision=revision)
            built = (
                _merged(model, adapter, hf)
                if adapter
                else _banked(model, bank or [], merges or [], hf)
            )
            lm = LanguageModel(built, tokenizer=tok)
        else:
            lm = LanguageModel(model, dispatch=True, **hf, **kwargs)
    else:
        lm = LanguageModel(model, tokenizer=tokenizer)
    lm.tokenizer.padding_side = "left"
    if lm.tokenizer.pad_token is None:
        lm.tokenizer.pad_token = lm.tokenizer.eos_token
    return lm


def save_model(model: Any, tokenizer: Any, name: str) -> Path:
    """A model and its tokenizer under <home>/models/<name>, where load(name) and the loupe/
    provider find it. model is a Hugging Face model or a LanguageModel over one."""
    from loupe.core import home

    path = home() / "models" / name
    getattr(model, "_model", model).save_pretrained(path)
    tokenizer.save_pretrained(path)
    return path


def tokenizer(path: str, revision: str | None = None) -> Any:
    """A saved tokenizer exactly as saved (AutoTokenizer would rebuild the family's default from
    model_type and drop a custom pre-tokenizer or decoder), else the Hub's."""
    if Path(path, "tokenizer.json").exists():
        return PreTrainedTokenizerFast.from_pretrained(path)
    return AutoTokenizer.from_pretrained(path, revision=revision)


def attention_kernel(attn: str) -> str:
    """The attn_implementation name for attn. A file.py:function spec imports that file and
    registers the function with AttentionInterface under the function's name, with the eager mask
    (additive float, [batch, 1, query, key]) as its mask; any other name passes through."""
    path, _, name = attn.rpartition(":")
    if not path.endswith(".py"):
        return attn
    import importlib.util

    from transformers import AttentionInterface
    from transformers.masking_utils import AttentionMaskInterface, eager_mask

    spec = importlib.util.spec_from_file_location(f"loupe_kernel_{Path(path).stem}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    AttentionInterface.register(name, getattr(module, name))
    AttentionMaskInterface.register(name, eager_mask)
    return name


def _merged(model: str, adapter: str | Path, hf: dict[str, Any]) -> Any:
    try:
        from peft import PeftModel
    except ImportError as exc:
        raise ImportError("loading an adapter needs the train extra: loupelab[train]") from exc
    from transformers import AutoModelForCausalLM

    base = AutoModelForCausalLM.from_pretrained(model, **hf)
    return PeftModel.from_pretrained(base, str(adapter)).merge_and_unload()


def _banked(model: str, names: list[str], merges: list[dict[str, Any]], hf: dict[str, Any]) -> Any:
    from transformers import AutoModelForCausalLM

    from loupe.models.adapters import activate, bank, merge

    base = AutoModelForCausalLM.from_pretrained(model, **hf)
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


def out_proj(attn: Any) -> Any:
    """An attention module's output projection, as an nnsight envoy."""
    return _first(attn, OUT_PATHS)


def n_heads(lm: LanguageModel) -> int:
    """Attention heads per layer, from the model's config."""
    config: Any = lm._model.config
    return int(getattr(config, "num_attention_heads", None) or config.n_head)


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

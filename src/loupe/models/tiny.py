"""A tiny randomly initialised Qwen2 with a word-level tokenizer, built offline.

For tests and for checking that a pipeline runs end to end without a download or a GPU. Its
outputs are noise; never read a result from it.
"""

from __future__ import annotations

from typing import cast

import torch
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
from transformers import PreTrainedTokenizerFast, Qwen2Config, Qwen2ForCausalLM

from loupe.models.load import load

VOCAB_TEXT = (
    "the a an is are was it this that I you we they not no yes sure sorry can cannot help "
    "what how why who where when which answer question think right wrong true false please "
    "write tell explain make build give me a an of to in on for with about story poem recipe "
    "cat dog sky blue red water fire bomb hack steal code python list steps tutorial . , ? ! "
    "poison weapon virus gun drug cake song game here"
)

CHAT_TEMPLATE = (
    "{% for m in messages %}<{{ m['role'] }}> {{ m['content'] }} {% endfor %}"
    "{% if add_generation_prompt %}<assistant>{% endif %}"
)


def tokenizer() -> PreTrainedTokenizerFast:
    specials = ["<unk>", "<pad>", "<eos>", "<user>", "<assistant>", "<system>"]
    tok = Tokenizer(models.WordLevel(unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.decoder = decoders.WordPiece()  # join words with spaces, also after a save and reload
    tok.train_from_iterator([VOCAB_TEXT], trainers.WordLevelTrainer(special_tokens=specials))
    out = PreTrainedTokenizerFast(
        tokenizer_object=tok, unk_token="<unk>", pad_token="<pad>", eos_token="<eos>"
    )
    out.chat_template = CHAT_TEMPLATE
    return out


def tiny(
    layers: int = 4,
    hidden: int = 32,
    seed: int = 0,
    train: list[tuple[str, str]] | None = None,
    steps: int = 300,
):
    """A LanguageModel over a Qwen2 small enough to run anywhere in milliseconds.

    Random by default. With `train`, (user message, reply) pairs, it is first fit to give those
    replies, which plants a known behaviour for checking that an analysis finds it.
    """
    tok = tokenizer()
    cfg = Qwen2Config(
        vocab_size=len(tok),
        hidden_size=hidden,
        intermediate_size=hidden * 2,
        num_hidden_layers=layers,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=256,
        tie_word_embeddings=True,
        pad_token_id=cast(int, tok.pad_token_id),
        eos_token_id=cast(int, tok.eos_token_id),
    )
    torch.manual_seed(seed)
    model = Qwen2ForCausalLM(cfg)
    if train:
        _fit(model, tok, train, steps)
    return load(model.eval(), tokenizer=tok)


def _fit(model, tok, pairs: list[tuple[str, str]], steps: int) -> None:
    """Full-batch AdamW on the reply tokens only."""
    ids, labels = [], []
    for user, reply in pairs:
        prompt = tok.apply_chat_template([{"role": "user", "content": user}], tokenize=False,
                                         add_generation_prompt=True)  # fmt: skip
        p = tok.encode(str(prompt), add_special_tokens=False)
        r = tok.encode(f"{reply} <eos>", add_special_tokens=False)
        ids.append(p + r)
        labels.append([-100] * len(p) + r)
    width = max(map(len, ids))
    pad = cast(int, tok.pad_token_id)
    x = torch.tensor([[pad] * (width - len(i)) + i for i in ids])
    y = torch.tensor([[-100] * (width - len(label)) + label for label in labels])
    mask = (torch.arange(width) >= torch.tensor([width - len(i) for i in ids])[:, None]).long()
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3)
    model.train()
    for _ in range(steps):
        loss = model(input_ids=x, attention_mask=mask, labels=y).loss
        opt.zero_grad()
        loss.backward()
        opt.step()

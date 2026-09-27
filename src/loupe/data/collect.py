"""Distillation data: a teacher's replies to prompts, as Examples, and the checks a small model's
training set needs before any score on it means something.

collect asks any Inspect model (a local vLLM or Ollama endpoint through openai-api, or loupe/ for a
local model) and writes Examples, so the teacher's output goes through verify, review and curate
like any trace. split assigns each example to train, dev or test by a hash of its prompt, so a
split survives re-collection and a prompt never lands in two splits. overlap flags evaluation
items sharing a word n-gram (13 by default, as in GPT-3's contamination check) with training text.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from loupe.data.example import Example, fingerprint

Prompt = str | list[dict[str, Any]]


def collect(
    prompts: Sequence[Prompt],
    teacher: str,
    system: str | None = None,
    max_tokens: int = 1024,
    samples: int = 1,
    **model_args: Any,
) -> list[Example]:
    """Each prompt's reply from the teacher, samples per prompt, exact duplicates dropped."""
    from inspect_ai.model import (
        ChatMessageAssistant,
        ChatMessageSystem,
        ChatMessageUser,
        GenerateConfig,
        get_model,
    )

    model = get_model(teacher, config=GenerateConfig(max_tokens=max_tokens), **model_args)
    kinds = {
        "user": ChatMessageUser,
        "assistant": ChatMessageAssistant,
        "system": ChatMessageSystem,
    }

    def messages(p: Prompt) -> list[dict[str, Any]]:
        head = [{"role": "system", "content": system}] if system else []
        return head + ([{"role": "user", "content": p}] if isinstance(p, str) else list(p))

    async def ask(p: Prompt) -> list[Example]:
        sent = messages(p)
        chat = [kinds[m["role"]](content=m["content"]) for m in sent]
        out = []
        for n in range(samples):
            reply = (await model.generate(chat)).completion
            key = hashlib.sha256(json.dumps([sent, n], sort_keys=True).encode()).hexdigest()
            args = json.dumps(model_args, sort_keys=True)
            meta = {"source": "teacher", "model": teacher, "max_tokens": str(max_tokens),
                    "sample": str(n), "model_args": args}  # fmt: skip
            out.append(Example(id=f"teacher-{key[:16]}", messages=sent, reply=reply, meta=meta,
                               at=datetime.now(UTC)))  # fmt: skip
        return out

    async def run() -> list[Example]:
        return [e for batch in await asyncio.gather(*map(ask, prompts)) for e in batch]

    return dedup(asyncio.run(run()))


def dedup(examples: Iterable[Example]) -> list[Example]:
    """The examples without exact repeats of what would be trained on, first kept."""
    seen: set[str] = set()
    out = []
    for e in examples:
        if (f := fingerprint(e)) not in seen:
            seen.add(f)
            out.append(e)
    return out


def bucket(text: str) -> float:
    """A stable number in [0, 1) from a hash of the text, for splits that survive re-collection."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 16**8


def split(example: Example, dev: float = 0.1, test: float = 0.1) -> str:
    """train, dev or test, from a hash of the prompt alone."""
    u = bucket(json.dumps(example.messages, sort_keys=True))
    return "test" if u < test else "dev" if u < test + dev else "train"


def plain(prompt: Prompt) -> str:
    """A prompt's text: the string, or its messages' contents joined."""
    if isinstance(prompt, str):
        return prompt
    return " ".join(str(m.get("content", "")) for m in prompt)


def ngrams(text: str, n: int = 13) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def overlap(train: Iterable[str], evals: dict[str, str], n: int = 13) -> list[str]:
    """Ids of the evaluation items that share a word n-gram with any training text."""
    seen: set[tuple[str, ...]] = set()
    for text in train:
        seen |= ngrams(text, n)
    return [i for i, text in evals.items() if ngrams(text, n) & seen]

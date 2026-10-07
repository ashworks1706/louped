"""Is a training set sound? Each pair's flags, read from the set's own rows.

A pair is a prompt (chat messages) and the reply trained toward (chosen); a DPO pair also has the
reply trained away from (rejected). An SFT set is louped's Examples: the reply is the chosen one.

- chosen_in_prompt: the chosen text, lowercased with whitespace collapsed, is inside the text of
  the prompt (every turn, the system turn included). The model learns to copy its input.
- length_only (DPO): the replies differ mostly in length. The longer has at least LENGTH_RATIO
  times the words of the shorter, and the shorter is a prefix of the longer or the two word sets
  overlap by Jaccard JACCARD or more.

A set warns when SHARE_WARN or more of its pairs carry a flag. Each pair's label says how its
chosen reply was picked. louped builds SFT sets (export or collect, then review and curate), so
it knows; it builds no DPO pairs, so their label is unknown.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from louped.data.example import Example, text_of

Flag = Literal["chosen_in_prompt", "length_only"]
FLAGS: tuple[Flag, ...] = ("chosen_in_prompt", "length_only")
Format = Literal["dpo", "sft"]

LENGTH_RATIO = 1.5
JACCARD = 0.8
SHARE_WARN = 0.2
UNKNOWN = "unknown"


class Preference(BaseModel):
    """A DPO row: the prompt as chat messages, the two replies as assistant text."""

    prompt: list[dict[str, Any]]
    chosen: str
    rejected: str


class Pair(BaseModel):
    #: The row's place in the file, from 0.
    index: int
    prompt: list[dict[str, Any]]
    chosen: str
    rejected: str | None = None
    #: How the chosen reply was picked; "unknown" for a set louped did not build.
    label: str
    flags: list[Flag]


class SetReport(BaseModel):
    format: Format
    rows: int
    #: Pairs with each flag.
    counts: dict[str, int]
    #: Pairs by how their chosen reply was picked.
    labels: dict[str, int]
    #: What a flag's share says about the whole set, when it is SHARE_WARN or more.
    warnings: list[str]
    pairs: list[Pair]


def normalize(text: str) -> str:
    """Lowercase, whitespace collapsed to single spaces."""
    return " ".join(text.lower().split())


def words(text: str) -> list[str]:
    """Lowercase words, and runs of punctuation, each its own token."""
    return re.findall(r"\w+|[^\w\s]+", text.lower())


def chosen_in_prompt(prompt: list[dict[str, Any]], chosen: str) -> bool:
    said = normalize(chosen)
    return bool(said) and said in normalize("\n".join(text_of(m) for m in prompt))


def length_only(chosen: str, rejected: str) -> bool:
    a, b = sorted((words(chosen), words(rejected)), key=len)
    if not b or len(b) < LENGTH_RATIO * max(1, len(a)):
        return False
    union = set(a) | set(b)
    return b[: len(a)] == a or len(set(a) & set(b)) / len(union) >= JACCARD


def pair(
    index: int, prompt: list[dict[str, Any]], chosen: str, rejected: str | None, label: str
) -> Pair:
    """One row as a Pair, with its flags."""
    found: list[Flag] = []
    if chosen_in_prompt(prompt, chosen):
        found.append("chosen_in_prompt")
    if rejected is not None and length_only(chosen, rejected):
        found.append("length_only")
    return Pair(index=index, prompt=prompt, chosen=chosen, rejected=rejected, label=label,
                flags=found)  # fmt: skip


def sft_label(example: Example) -> str:
    """Where an Example's reply came from and who reviewed it, as louped's pipeline recorded."""
    source = example.meta.get("source")
    if not source:
        return UNKNOWN
    model = example.meta.get("model")
    said = f"reply from {source}" + (f" ({model})" if model else "")
    return f"{said}, {example.meta.get('review', 'unreviewed')}"


def detect(path: Path) -> Format:
    """dpo for rows with chosen and rejected, sft for louped's Examples (messages and reply)."""
    with path.open(encoding="utf-8") as f:
        first = next((line for line in f if line.strip()), None)
    if first is None:
        raise ValueError(f"{path} is empty")
    keys = set(json.loads(first))
    if {"chosen", "rejected"} <= keys:
        return "dpo"
    if "reply" in keys or "messages" in keys:
        return "sft"
    raise ValueError(f"{path}: rows with {sorted(keys)} are neither DPO pairs nor Examples")


def read_pairs(path: Path, format: Format) -> list[Pair]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out: list[Pair] = []
    for i, line in enumerate(lines):
        if format == "dpo":
            p = Preference.model_validate_json(line)
            out.append(pair(i, p.prompt, p.chosen, p.rejected, UNKNOWN))
        else:
            e = Example.model_validate_json(line)
            out.append(pair(i, e.messages, e.reply, None, sft_label(e)))
    return out


def report(pairs: list[Pair], format: Format) -> SetReport:
    n = len(pairs)
    shown = FLAGS if format == "dpo" else ("chosen_in_prompt",)
    counts = {f: sum(f in p.flags for p in pairs) for f in shown}
    labels: dict[str, int] = {}
    for p in pairs:
        labels[p.label] = labels.get(p.label, 0) + 1
    said = {"chosen_in_prompt": "chosen replies are already in their prompt: the set teaches "
                                "copying the input",
            "length_only": "pairs differ mostly in length: the set teaches length, not "
                           "content"}  # fmt: skip
    warnings = [f"{k} of {n} {said[f]} ({k / n:.0%})"
                for f, k in counts.items() if n and k / n >= SHARE_WARN]  # fmt: skip
    return SetReport(format=format, rows=n, counts=counts, labels=labels, warnings=warnings,
                     pairs=pairs)  # fmt: skip


def check(path: Path, format: Format | None = None) -> SetReport:
    """A training file's pairs with their flags, and what they say about the set."""
    format = format or detect(path)
    return report(read_pairs(path, format), format)


def sft_report(examples: list[Example]) -> SetReport:
    """An SFT set's report: each Example's reply is its chosen reply."""
    return report([pair(i, e.messages, e.reply, None, sft_label(e))
                   for i, e in enumerate(examples)], "sft")  # fmt: skip

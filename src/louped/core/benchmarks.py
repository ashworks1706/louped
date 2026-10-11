"""Benchmarks made from a Hugging Face dataset with a field mapping, kept in louped.toml:

    [benchmarks.gsm8k]
    dataset = "openai/gsm8k"
    config = "main"
    split = "test"
    input = "question"
    target = "answer"
    scorer = "match"

Each one is the Inspect task louped/<name> (louped.inspect_ext.benchmark builds it), so `inspect
eval louped/gsm8k` and Launch's eval run it like any other task. No code per benchmark.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from louped.core.project import FILE, config

#: match: Inspect's match(), the target at the end of the reply (numbers compared as numbers);
#: choice: a multiple-choice question, answered by letter; judge: louped's judge model grades the
#: reply against the target (Inspect's model_graded_fact on core.judges.MODEL, a local model).
Scorer = Literal["match", "choice", "judge"]
#: A benchmark's name: its table in louped.toml and its task louped/<name>.
NAME = r"^[a-z0-9][a-z0-9_-]{0,63}$"
#: A Hub dataset id.
DATASET = r"^[\w.-]+(/[\w.-]+)?$"


class Benchmark(BaseModel):
    """A Hub dataset as an eval: which rows, and which field is the input, the target and the
    choices."""

    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(pattern=DATASET)
    #: The dataset's configuration (subset), when it has more than one.
    config: str | None = None
    split: str = "test"
    #: The field each sample's prompt is read from.
    input: str
    #: The field the reply is scored against: text, or for choice the right choice's index,
    #: letter or text.
    target: str
    #: The field holding a list of choices; needed by the choice scorer.
    choices: str | None = None
    scorer: Scorer = "match"

    @model_validator(mode="after")
    def _choices_for_choice(self) -> Benchmark:
        if self.scorer == "choice" and not self.choices:
            raise ValueError("the choice scorer needs a choices field")
        return self


def task_name(name: str) -> str:
    """The Inspect task a benchmark runs as."""
    return f"louped/{name}"


def benchmarks() -> dict[str, Benchmark]:
    """The [benchmarks.<name>] tables of the project's louped.toml, by name; none outside a
    project. A table that does not read as one is a ValueError naming it."""
    tables = config().get("benchmarks", {})
    if not isinstance(tables, dict):
        raise ValueError(f"{FILE}: [benchmarks] holds one [benchmarks.<name>] table each")
    out: dict[str, Benchmark] = {}
    for name, table in tables.items():
        if not re.match(NAME, name):
            raise ValueError(f"{FILE} [benchmarks.{name}]: a name is lowercase letters, digits, - "
                             "and _")  # fmt: skip
        try:
            out[name] = Benchmark.model_validate(table)
        except ValidationError as exc:
            raise ValueError(f"{FILE} [benchmarks.{name}]: {exc}") from exc
    return out

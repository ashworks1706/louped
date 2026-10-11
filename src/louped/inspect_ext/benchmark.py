"""The Inspect task behind a benchmark made from a Hugging Face dataset (louped.core.benchmarks):
the dataset read with Inspect's hf_dataset, each row made a Sample by the benchmark's field
mapping, and the scorer it names. It runs as louped/<name> (_registry registers one per
benchmark in louped.toml):

    inspect eval louped/gsm8k --model louped/Qwen/Qwen2.5-0.5B-Instruct --limit 50
"""

from __future__ import annotations

import string
from collections.abc import Callable
from typing import Any

from inspect_ai import Task
from inspect_ai.dataset import Sample, hf_dataset
from inspect_ai.scorer import Scorer, choice, match, model_graded_fact
from inspect_ai.solver import Solver, generate, multiple_choice

from louped.core.benchmarks import Benchmark, benchmarks, task_name
from louped.core.judges import MODEL

LETTERS = string.ascii_uppercase


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _letter(value: Any, choices: list[str]) -> str:
    """The right choice as Inspect's choice scorer reads it, a letter, from an index, a letter
    or the choice's own text."""
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(choices):
        return LETTERS[value]
    if isinstance(value, str):
        given = value.strip()
        if len(given) == 1 and given.upper() in LETTERS[: len(choices)]:
            return given.upper()
        if given in choices:
            return LETTERS[choices.index(given)]
    raise ValueError(f"target {value!r} is not an index, a letter or the text of one of "
                     f"{len(choices)} choices")  # fmt: skip


def record_to_sample(spec: Benchmark) -> Callable[[dict[str, Any]], Sample]:
    """A dataset row as a Sample: input from spec.input, target from spec.target (a letter for
    the choice scorer), choices from spec.choices. A row without a mapped field is a ValueError
    naming the fields it has."""

    def to_sample(record: dict[str, Any]) -> Sample:
        fields = [f for f in (spec.input, spec.target, spec.choices) if f]
        missing = [f for f in fields if f not in record]
        if missing:
            raise ValueError(f"{spec.dataset}: a row has no field {', '.join(missing)}; its "
                             f"fields are {', '.join(sorted(record))}")  # fmt: skip
        choices = None
        if spec.choices:
            found = record[spec.choices]
            if not isinstance(found, list):
                raise ValueError(f"{spec.dataset}: {spec.choices} is {type(found).__name__}, "
                                 "not a list of choices")  # fmt: skip
            choices = [_text(c) for c in found]
        raw = record[spec.target]
        if spec.scorer == "choice":
            assert choices is not None  # Benchmark checks the choice scorer has choices
            target: str | list[str] = _letter(raw, choices)
        else:
            target = [_text(t) for t in raw] if isinstance(raw, list) else _text(raw)
        return Sample(input=_text(record[spec.input]), target=target, choices=choices)

    return to_sample


def _scoring(spec: Benchmark) -> tuple[Solver, Scorer]:
    if spec.scorer == "choice":
        return multiple_choice(), choice()
    if spec.scorer == "judge":
        return generate(), model_graded_fact(model=MODEL)
    return generate(), match()


def benchmark(name: str) -> Task:
    """The benchmark louped.toml names [benchmarks.<name>], as an Inspect task."""
    found = benchmarks()
    if name not in found:
        raise ValueError(f"no [benchmarks.{name}] in louped.toml; it has {sorted(found) or 'none'}")
    spec = found[name]
    dataset = hf_dataset(spec.dataset, split=spec.split, name=spec.config,
                         sample_fields=record_to_sample(spec), auto_id=True)  # fmt: skip
    solver, scorer = _scoring(spec)
    return Task(dataset=dataset, solver=solver, scorer=scorer, name=task_name(name),
                metadata={"benchmark": name, **spec.model_dump(exclude_none=True)})  # fmt: skip

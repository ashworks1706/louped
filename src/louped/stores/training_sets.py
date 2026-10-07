"""The training sets louped knows, each checked for soundness (louped.data.pairs).

A set is a JSONL file that one of these names: a training config in experiments/ (a YAML file
that starts `# louped train sft` or `# louped train dpo`), a training run (its dataset param), or
the data pipeline (<home>/data/<name>/*.jsonl). Its format is the recipe's when one names it,
else read from its first row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from louped.core import experiments_dir, home
from louped.data import pairs
from louped.stores import mlflow_runs
from louped.stores.runs import NotFound

#: The most pairs one request returns; the counts cover every pair.
MAX_PAIRS = 1000


class TrainingSet(BaseModel):
    #: The file, absolute.
    path: str
    format: pairs.Format | None
    rows: int
    counts: dict[str, int]
    labels: dict[str, int]
    warnings: list[str]
    #: Training configs naming it, relative to experiments/.
    configs: list[str]
    #: Training runs that trained on it.
    runs: list[str]
    #: Why it could not be read: missing, or rows louped does not know.
    error: str | None


class SetPairs(BaseModel):
    path: str
    report: pairs.SetReport
    #: Pairs with each flag first, then the rest, at most MAX_PAIRS of them.
    shown: int


@dataclass
class _Known:
    format: pairs.Format | None
    configs: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)


def _under_home(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else home() / p


def _found() -> dict[str, _Known]:
    sets: dict[str, _Known] = {}

    def add(path: Path, format: pairs.Format | None) -> _Known:
        known = sets.setdefault(str(path.resolve()), _Known(format))
        known.format = known.format or format
        return known

    for cfg in sorted(experiments_dir().glob("*/*.yaml")):
        text = cfg.read_text(encoding="utf-8")
        m = re.match(r"# louped train (sft|dpo)\b", text)
        dataset = m and (yaml.safe_load(text) or {}).get("dataset")
        if m and dataset:
            known = add(_under_home(str(dataset)), m[1])  # type: ignore[arg-type]
            known.configs.append(cfg.relative_to(experiments_dir()).as_posix())
    for run_id, recipe, dataset in mlflow_runs.training_datasets():
        if recipe in ("sft", "dpo"):
            add(Path(dataset), recipe).runs.append(run_id)  # type: ignore[arg-type]
    for path in sorted((home() / "data").glob("*/*.jsonl")):
        add(path, None)
    return sets


@lru_cache(maxsize=16)
def _check(path: str, mtime: float, format: pairs.Format | None) -> pairs.SetReport:
    return pairs.check(Path(path), format)


def _report(path: str, known: _Known) -> pairs.SetReport | str:
    """The set's report, or why it could not be read."""
    file = Path(path)
    if not file.is_file():
        return f"no file at {file}"
    try:
        return _check(path, file.stat().st_mtime, known.format)
    except ValueError as exc:  # pydantic's ValidationError is one
        return str(exc).splitlines()[0]


def list_training_sets() -> list[TrainingSet]:
    """Every set louped knows, with its flag counts and warnings, by path."""
    out = []
    for path, known in sorted(_found().items()):
        found = _report(path, known)
        ok = not isinstance(found, str)
        out.append(TrainingSet(
            path=path, format=found.format if ok else known.format, rows=found.rows if ok else 0,
            counts=found.counts if ok else {}, labels=found.labels if ok else {},
            warnings=found.warnings if ok else [], configs=known.configs, runs=known.runs,
            error=None if ok else found,
        ))  # fmt: skip
    return out


def training_set_pairs(path: str) -> SetPairs:
    """One known set's pairs with their flags, flagged pairs first. NotFound for a path louped
    does not know as a training set, so this reads no other file."""
    known = _found().get(path)
    if known is None:
        raise NotFound(f"training set {path}")
    found = _report(path, known)
    if isinstance(found, str):
        raise ValueError(found)
    ordered = sorted(found.pairs, key=lambda p: (not p.flags, p.index))[:MAX_PAIRS]
    return SetPairs(path=path, report=found.model_copy(update={"pairs": ordered}),
                    shown=len(ordered))  # fmt: skip

"""Experiments are folders under experiments/, each with a README stating its question."""

from __future__ import annotations

import re

from loupe.core import experiments_dir
from loupe.stores.runs import list_runs
from loupe.stores.types import Experiment

_QUESTION = re.compile(r"^##\s+Question\s*$\n+(.+?)(?:\n\s*\n|\n##|\Z)", re.M | re.S)


def question(readme: str) -> str | None:
    """The first paragraph under '## Question', or None when there is none."""
    found = _QUESTION.search(readme)
    if not found:
        return None
    text = " ".join(found.group(1).split())
    return text or None


def list_experiments() -> list[Experiment]:
    root = experiments_dir()
    if not root.is_dir():
        return []
    runs = list_runs()
    out: list[Experiment] = []
    for folder in sorted(
        p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
    ):
        readme = folder / "README.md"
        out.append(
            Experiment(
                name=folder.name,
                question=question(readme.read_text(encoding="utf-8")) if readme.exists() else None,
                runs=[r for r in runs if r.experiment == folder.name],
            )
        )
    return out

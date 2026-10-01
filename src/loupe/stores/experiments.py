"""Experiments are folders under experiments/, each with a README stating its question.

A README opens with front matter naming its domain and status:

    ---
    domain: mechanisms
    status: active
    ---

Domains belong to one of two research axes, behaviour and efficiency, or to the checks that
loupe reproduces known results. The axis is read from the domain, so a README names only the
domain. A README without front matter, or with a domain or status not listed here, is an error
naming the folder, not an experiment filed under a default.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from loupe.core import experiments_dir
from loupe.stores.runs import NotFound, list_runs
from loupe.stores.types import (
    Axis,
    Domain,
    Experiment,
    ExperimentDetail,
    RunSummary,
    Status,
)

#: Each domain's axis and title, in the order the Experiments page shows them.
DOMAINS: dict[Domain, tuple[Axis, str]] = {
    "mechanisms": ("behavior", "Mechanisms"),
    "honesty": ("behavior", "Sycophancy and honesty"),
    "conditioning": ("behavior", "Steering and conditioning"),
    "agents": ("behavior", "Agent behavior"),
    "context": ("efficiency", "Context and retrieval inside the model"),
    "inference": ("efficiency", "Inference cost and kernels"),
    "specialisation": ("efficiency", "Small and specialised models"),
    "reproduction": ("checks", "Reproducing known results"),
}

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)


class BadExperiment(ValueError):
    """An experiment folder the page cannot file: no README, or front matter missing or unknown."""


def _paragraph(readme: str, heading: str) -> str | None:
    """The first paragraph under '## heading': its lines up to a blank line or the next heading,
    HTML comments (the scaffold's hints) left out. None when the section is missing or empty."""
    lines = _COMMENT.sub("", readme).splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == f"## {heading}")
    except StopIteration:
        return None
    para: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#") or (para and not line.strip()):
            break
        if line.strip():
            para.append(line)
    # The page shows plain text, so inline code marks go; the words inside them stay.
    text = " ".join(" ".join(para).replace("`", "").split())
    return text or None


def question(readme: str) -> str | None:
    """The first paragraph under '## Question', or None when there is none."""
    return _paragraph(readme, "Question")


def result(readme: str) -> str | None:
    """The first paragraph under '## Result', or None when there is none."""
    return _paragraph(readme, "Result")


def front_matter(readme: str, name: str) -> tuple[Domain, Status]:
    """The domain and status a README declares; raises naming the experiment when either is
    missing or not one loupe knows."""
    found = _FRONT.match(readme)
    if not found:
        raise BadExperiment(
            f"experiments/{name}/README.md has no front matter with domain and status"
        )
    fields = dict(
        (k.strip(), v.strip())
        for k, v in (line.split(":", 1) for line in found.group(1).splitlines() if ":" in line)
    )
    domain, status = fields.get("domain"), fields.get("status")
    if domain not in DOMAINS:
        raise BadExperiment(f"experiments/{name}: domain {domain!r} is not one of {list(DOMAINS)}")
    if status not in get_args(Status):
        raise BadExperiment(
            f"experiments/{name}: status {status!r} is not one of {get_args(Status)}"
        )
    return domain, status  # type: ignore[return-value]


def _folders() -> list[Path]:
    root = experiments_dir()
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def _read(folder: Path, runs: list[RunSummary]) -> tuple[Experiment, str]:
    """The experiment in a folder, and its README without the front matter."""
    readme_path = folder / "README.md"
    if not readme_path.exists():
        raise BadExperiment(f"experiments/{folder.name} has no README.md")
    readme = readme_path.read_text(encoding="utf-8")
    domain, status = front_matter(readme, folder.name)
    experiment = Experiment(
        name=folder.name,
        axis=DOMAINS[domain][0],
        domain=domain,
        domain_title=DOMAINS[domain][1],
        status=status,
        question=question(readme),
        result=result(readme),
        runs=[r for r in runs if r.experiment == folder.name],
    )
    return experiment, _FRONT.sub("", readme, count=1).lstrip()


def list_experiments() -> list[Experiment]:
    runs = list_runs()
    out = [_read(folder, runs)[0] for folder in _folders()]
    order = list(DOMAINS)
    return sorted(out, key=lambda e: (order.index(e.domain), e.status != "active", e.name))


def _without(readme: str, *headings: str) -> str:
    """The README with the named '## ' sections left out, each up to the next '## ' heading."""
    out: list[str] = []
    skipping = False
    for line in readme.splitlines(keepends=True):
        if line.startswith("## "):
            skipping = line[3:].strip() in headings
        if not skipping:
            out.append(line)
    return "".join(out)


def get_experiment(name: str) -> ExperimentDetail:
    """One experiment with its README; NotFound when no folder has that name. The README leaves
    out Question and Result, which the experiment already carries as fields."""
    folder = next((f for f in _folders() if f.name == name), None)
    if folder is None:
        raise NotFound(name)
    experiment, readme = _read(folder, list_runs())
    return ExperimentDetail(
        **experiment.model_dump(), readme=_without(readme, "Question", "Result")
    )

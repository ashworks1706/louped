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
    """The experiments: folders with a README.md. A folder without one is not an experiment, such
    as what is left of a deleted one after git removes its tracked files."""
    root = experiments_dir()
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_")) and (p / "README.md").is_file()
    )


def _read(folder: Path, runs: list[RunSummary]) -> tuple[Experiment, str]:
    """The experiment in a folder, and its README without the front matter."""
    readme = (folder / "README.md").read_text(encoding="utf-8")
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


#: A new experiment's README: the sections every question fills in, as the Experiments page reads.
TEMPLATE = """---
domain: {domain}
status: active
---

# {name}

## Question

<!-- One sentence that comes out yes or no, or as a number. -->

## Observation

<!-- What failed or bottlenecked, as seen, not as interpreted. -->

## Hypotheses

<!-- What might cause it, including the explanations that compete with yours. -->

## Baseline

<!-- The nearest existing method, and the simplest thing that might already work. -->

## Test

<!-- The controlled comparison that tells the hypotheses apart: conditions, metric, seeds. -->

## Stop if

<!-- The result that weakens the idea or makes it impractical. -->

## Run

## Result

## Next
"""


#: A new experiment's run.py: launchable from the app, its Args the form, its run filed under it.
RUN = '''"""{name}: what one run measures, in a line; Launch shows it."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import tyro

from loupe.tracking import start_run

EXPERIMENT = "{name}"


@dataclass
class Args:
    """Each field is an option on Launch; the docstring under it is its help."""

    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    """A Hub id, a path, or a name under <home>/models."""
    seed: int = 0


def main(args: Args) -> None:
    with start_run(EXPERIMENT, name=args.model, params=asdict(args), seed=args.seed):
        # The Test in README.md. Numbers: mlflow.log_metrics. Figures: a view from
        # loupe.analysis.views, logged with loupe.tracking.log_json under views/.
        raise NotImplementedError("the Test in README.md")


if __name__ == "__main__":
    main(tyro.cli(Args))
'''


def scaffold(name: str, domain: str) -> Path:
    """experiments/<name>/ with its README to fill in and a run.py to write, active in domain."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise BadExperiment(f"{name!r}: a name is lowercase letters, digits and dashes")
    if domain not in DOMAINS:
        raise BadExperiment(f"domain {domain!r} is not one of {list(DOMAINS)}")
    folder = experiments_dir() / name
    if folder.exists():
        raise BadExperiment(f"experiments/{name} exists")
    folder.mkdir(parents=True)
    (folder / "README.md").write_text(TEMPLATE.format(name=name, domain=domain), encoding="utf-8")
    (folder / "run.py").write_text(RUN.format(name=name), encoding="utf-8")
    return folder

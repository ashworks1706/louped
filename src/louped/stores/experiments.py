"""Experiments are folders under experiments/, each with a README stating its question.

A README opens with front matter naming its domain and status:

    ---
    domain: mechanisms
    status: active
    ---

Domains belong to one of two research axes, behaviour and efficiency, or to the checks that
louped reproduces known results. The axis is read from the domain, so a README names only the
domain. A project lists its domains in louped.toml; without that list it has DEFAULT_DOMAINS:

    [domains.honesty]
    axis = "behavior"
    title = "Sycophancy and honesty"

A README without front matter, or with a domain or status the project does not list, is an error
naming the folder, not an experiment filed under a default.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from louped.core import experiments_dir, trash
from louped.core.project import config
from louped.stores.runs import NotFound, list_runs
from louped.stores.types import (
    Axis,
    Domain,
    Experiment,
    ExperimentDetail,
    RunSummary,
    Status,
)

#: Each domain's axis and title, in the order the Experiments page shows them, for a project whose
#: louped.toml lists none.
DEFAULT_DOMAINS: dict[Domain, tuple[Axis, str]] = {
    "mechanisms": ("behavior", "Mechanisms"),
    "honesty": ("behavior", "Sycophancy and honesty"),
    "conditioning": ("behavior", "Steering and conditioning"),
    "agents": ("behavior", "Agent behavior"),
    "context": ("efficiency", "Context and retrieval inside the model"),
    "inference": ("efficiency", "Inference cost and kernels"),
    "specialisation": ("efficiency", "Small and specialised models"),
    "reproduction": ("checks", "Reproducing known results"),
}


def domains() -> dict[Domain, tuple[Axis, str]]:
    """The project's domains from louped.toml, in its order; DEFAULT_DOMAINS when it lists none.
    A domain with an unknown axis or no title is an error naming it."""
    listed = config().get("domains")
    if not listed:
        return DEFAULT_DOMAINS
    out: dict[Domain, tuple[Axis, str]] = {}
    for key, entry in listed.items():
        axis, title = entry.get("axis"), entry.get("title")
        if axis not in get_args(Axis) or not isinstance(title, str) or not title:
            raise BadExperiment(
                f"louped.toml: domain {key!r} needs an axis, one of {get_args(Axis)}, and a title"
            )
        out[key] = (axis, title)
    return out


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


def _fields(readme: str) -> dict[str, str] | None:
    """The front matter's key: value lines, or None when the README has none."""
    found = _FRONT.match(readme)
    if not found:
        return None
    return dict(
        (k.strip(), v.strip())
        for k, v in (line.split(":", 1) for line in found.group(1).splitlines() if ":" in line)
    )


def declared_extras(name: str) -> list[str] | None:
    """The package extras an experiment's README declares its run needs (`extras: tracking,
    interp` in its front matter), which an exported job installs instead of the defaults; None
    when it declares none or the experiment is not found."""
    readme = experiments_dir() / name / "README.md"
    if not readme.is_file():
        return None
    value = (_fields(readme.read_text(encoding="utf-8")) or {}).get("extras")
    return [e.strip() for e in value.split(",") if e.strip()] if value else None


def front_matter(readme: str, name: str) -> tuple[Domain, Status]:
    """The domain and status a README declares; raises naming the experiment when either is
    missing or not one louped knows."""
    fields = _fields(readme)
    if fields is None:
        raise BadExperiment(
            f"experiments/{name}/README.md has no front matter with domain and status"
        )
    domain, status = fields.get("domain"), fields.get("status")
    known = domains()
    if domain not in known:
        raise BadExperiment(f"experiments/{name}: domain {domain!r} is not one of {list(known)}")
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
    axis, title = domains()[domain]
    experiment = Experiment(
        name=folder.name,
        axis=axis,
        domain=domain,
        domain_title=title,
        status=status,
        question=question(readme),
        result=result(readme),
        runs=[r for r in runs if r.experiment == folder.name],
    )
    return experiment, _FRONT.sub("", readme, count=1).lstrip()


def list_experiments() -> list[Experiment]:
    runs = list_runs()
    out = [_read(folder, runs)[0] for folder in _folders()]
    order = list(domains())
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


def _folder(name: str) -> Path:
    found = next((f for f in _folders() if f.name == name), None)
    if found is None:
        raise NotFound(name)
    return found


def read_readme(name: str) -> str:
    """An experiment's README as written, front matter and all."""
    return (_folder(name) / "README.md").read_text(encoding="utf-8")


def write_readme(name: str, text: str) -> None:
    """Replace an experiment's README; refused (BadExperiment) when its front matter would no
    longer name a domain and status, which would take the experiment off its page."""
    folder = _folder(name)
    front_matter(text, name)
    (folder / "README.md").write_text(text, encoding="utf-8")


def delete_experiment(name: str) -> Path:
    """Move an experiment's folder to the trash; its runs stay, under its name. Returns where."""
    return trash(_folder(name), "experiments")


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

from louped.tracking import start_run

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
        # louped.analysis.views, logged with louped.tracking.log_json under views/.
        raise NotImplementedError("the Test in README.md")


if __name__ == "__main__":
    main(tyro.cli(Args))
'''


def scaffold(name: str, domain: str) -> Path:
    """experiments/<name>/ with its README to fill in and a run.py to write, active in domain."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise BadExperiment(f"{name!r}: a name is lowercase letters, digits and dashes")
    known = domains()
    if domain not in known:
        raise BadExperiment(f"domain {domain!r} is not one of {list(known)}")
    folder = experiments_dir() / name
    if folder.exists():
        raise BadExperiment(f"experiments/{name} exists")
    folder.mkdir(parents=True)
    (folder / "README.md").write_text(TEMPLATE.format(name=name, domain=domain), encoding="utf-8")
    (folder / "run.py").write_text(RUN.format(name=name), encoding="utf-8")
    return folder

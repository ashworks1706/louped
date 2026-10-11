"""Projects group experiments: projects/<name>/README.md, beside experiments/.

A README opens with front matter (louped.stores.types.ProjectMeta), then the goal, background
and notes:

    ---
    title: Sycophancy under pushback
    status: active
    summary: When and why models cave when a user pushes back.
    tags: [honesty]
    links: {repo: https://github.com/me/pushback}
    models: [Qwen/Qwen2.5-0.5B-Instruct]
    ---

An experiment joins one with `project: <name>` in its own front matter; its folder stays under
experiments/. A project that experiments name but that has no README is listed as missing, not
left out. A README whose front matter does not parse is an error naming its folder.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from louped.core import projects_dir
from louped.core.paths import NAME
from louped.stores.experiments import FRONT, BadExperiment, list_experiments
from louped.stores.runs import NotFound
from louped.stores.types import Experiment, Project, ProjectDetail, ProjectMeta


class BadProject(BadExperiment):
    """A project folder louped cannot read: its README's front matter is missing or wrong."""


#: A new project's README text under its front matter.
BODY = """# {title}

## Goal

<!-- What the project is for, in one or two sentences. -->

## Background

<!-- What is known already, and the sources it rests on. -->

## Notes
"""


def _folders() -> list[Path]:
    root = projects_dir()
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_")) and (p / "README.md").is_file()
    )


def parse(readme: str, name: str) -> tuple[ProjectMeta, str]:
    """A README's front matter and the text under it; BadProject naming the folder when the front
    matter is missing, not YAML or not a project's."""
    found = FRONT.match(readme)
    if not found:
        raise BadProject(f"projects/{name}/README.md has no front matter (--- title: ... ---)")
    try:
        fields = yaml.safe_load(found.group(1))
        meta = ProjectMeta.model_validate(fields if fields is not None else {})
    except yaml.YAMLError as exc:
        raise BadProject(f"projects/{name}/README.md: front matter is not YAML: {exc}") from exc
    except ValidationError as exc:
        wrong = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'front matter'}: {e['msg']}"
            for e in exc.errors()
        )
        raise BadProject(f"projects/{name}/README.md: {wrong}") from exc
    if not meta.title:
        meta.title = name
    return meta, readme[found.end() :].lstrip()


def render(meta: ProjectMeta, body: str) -> str:
    """A README from front matter and text: title, status and summary always, the rest when
    set."""
    fields = meta.model_dump()
    kept = {k: v for k, v in fields.items() if v or k in ("title", "status", "summary")}
    front = yaml.safe_dump(kept, sort_keys=False, allow_unicode=True, width=1000)
    return f"---\n{front}---\n\n{body.lstrip()}"


def _folder(name: str) -> Path:
    found = next((f for f in _folders() if f.name == name), None)
    if found is None:
        raise NotFound(f"project {name}")
    return found


def _named(experiments: list[Experiment]) -> dict[str, list[Experiment]]:
    by: dict[str, list[Experiment]] = {}
    for e in experiments:
        if e.project:
            by.setdefault(e.project, []).append(e)
    return by


def list_projects() -> list[Project]:
    """Every project with its experiments' names, run count and last run, by name; a project
    that experiments name with no README comes last, marked missing."""
    experiments = _named(list_experiments())
    out: list[Project] = []
    for folder in _folders():
        meta, _ = parse((folder / "README.md").read_text(encoding="utf-8"), folder.name)
        out.append(_summary(folder.name, meta, experiments.get(folder.name, [])))
    known = {p.name for p in out}
    for name in sorted(set(experiments) - known):
        out.append(_summary(name, ProjectMeta(title=name), experiments[name], missing=True))
    return out


def _summary(name: str, meta: ProjectMeta, mine: list[Experiment], missing: bool = False):
    runs = [r for e in mine for r in e.runs]
    times = [r.created for r in runs if r.created is not None]
    return Project(**meta.model_dump(), name=name, experiments=[e.name for e in mine],
                   runs=len(runs), last_run=max(times, default=None), missing=missing)  # fmt: skip


def get_project(name: str) -> ProjectDetail:
    """One project with its README text, its experiments and their runs, newest first. A name
    only experiments give comes back missing; NotFound when nothing has that name."""
    mine = _named(list_experiments()).get(name, [])
    try:
        folder = _folder(name)
    except NotFound:
        if not mine:
            raise
        meta, body, missing = ProjectMeta(title=name), "", True
    else:
        meta, body = parse((folder / "README.md").read_text(encoding="utf-8"), name)
        missing = False
    runs = sorted((r for e in mine for r in e.runs), key=lambda r: r.created.timestamp()
                  if r.created else 0, reverse=True)  # fmt: skip
    return ProjectDetail(**meta.model_dump(), name=name, readme=body, experiments=mine,
                         runs=runs, missing=missing)  # fmt: skip


def create(name: str, meta: ProjectMeta) -> Path:
    """projects/<name>/README.md with its front matter and the sections to fill in. Refused
    (BadProject) for a name that is not lowercase letters, digits and -, or one that exists."""
    if not NAME.match(name):
        raise BadProject(f"{name!r}: a project's name is lowercase letters, digits and -")
    folder = projects_dir() / name
    if (folder / "README.md").exists():
        raise BadProject(f"projects/{name} exists")
    meta = meta.model_copy(update={"title": meta.title or name})
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "README.md").write_text(render(meta, BODY.format(title=meta.title)), "utf-8")
    return folder


def read_readme(name: str) -> str:
    """A project's README as written, front matter and all."""
    return (_folder(name) / "README.md").read_text(encoding="utf-8")


def write_readme(name: str, text: str) -> None:
    """Replace a project's README; refused (BadProject) when its front matter would not parse."""
    folder = _folder(name)
    parse(text, name)
    (folder / "README.md").write_text(text, encoding="utf-8")


def set_meta(name: str, meta: ProjectMeta) -> ProjectMeta:
    """Replace a project's front matter, keeping the text under it. Returns what was written."""
    folder = _folder(name)
    _, body = parse((folder / "README.md").read_text(encoding="utf-8"), name)
    meta = meta.model_copy(update={"title": meta.title or name})
    (folder / "README.md").write_text(render(meta, body), encoding="utf-8")
    return meta

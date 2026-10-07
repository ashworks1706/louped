"""Following a ref down to its evidence: a figure, the script that made it and the commit it ran
at, the item's record in every file that holds it, and the run with its commit.

A figure's marks stand for items when the figure says which (its `items`): then a mark's ref,
run:<run>/views/<figure>.json#<item>, traces to that item's rows. A figure or derived file that
`louped derive` made traces to its script (derived/<name>.py) and the commit in
derived/<name>.meta.json; one the run logged itself traces to the run's commit. A script's and a
run's step carry their code: the file at that commit on the forge the project's git remote names.
"""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from pydantic import TypeAdapter, ValidationError

from louped.core.git import pushed_to, remote_url, top, web_url
from louped.core.paths import experiment_folder, inside
from louped.core.project import base
from louped.core.refs import parse, ref
from louped.stores.items import folders, join_key, key_text, read_rows
from louped.stores.runs import NotFound, get_run, read_artifact
from louped.stores.types import (
    Code,
    ItemSource,
    PlotlyView,
    RunDetail,
    Trace,
    TraceStep,
    VegaView,
    View,
)

_VIEW: TypeAdapter[View] = TypeAdapter(View)
DERIVED = "derived"


def trace(text: str) -> Trace:
    """The chain behind a ref, from it down to the run. ValueError when the ref or what it names
    does not fit, NotFound when the run or file is not there."""
    at = parse(text)
    steps: list[TraceStep] = []
    source: ItemSource | None = None
    if at.scheme == "experiment":
        if at.path is None or not _is_view(at.path):
            raise ValueError("an experiment's ref names one of its figures: "
                             "experiment:<name>/views/<figure>.json")  # fmt: skip
        view = read_view(text)
        steps.append(_figure(ref("experiment", at.name, at.path), view))
        source = _items(view)
        if source is None or source.run is None:
            if at.item is not None:
                raise ValueError(f"{at.path} does not say which run's items its marks are")
            return Trace(ref=text, steps=steps)
        run_id = source.run
        own = None
    else:
        run_id = own = at.name
        artifacts = [a.path for a in get_run(run_id).artifacts]
        if at.path is not None and at.path not in artifacts:
            raise NotFound(f"run {run_id} has no {at.path}")
        if at.path is not None and _is_view(at.path):
            view = read_view(text)
            steps.append(_figure(ref("run", run_id, at.path), view))
            source = _items(view)
            if at.item is not None and source is None:
                raise ValueError(f"{at.path} does not say which items its marks are")
        steps.extend(_made_by(run_id, at.path, artifacts))
        if source is not None and source.run is not None:
            run_id = source.run
    if at.item is not None:
        folder = source.folder if source else _folder_of(at.path)
        steps.append(_item(run_id, folder, at.item))
    steps.append(_run(run_id))
    if own is not None and own != run_id:
        steps.append(_run(own))  # the run that logged the figure, besides the one it draws on
    return Trace(ref=text, steps=steps)


def read_view(text: str) -> View:
    """The figure a ref names: run:<id>/views/<name>.json or experiment:<name>/views/<name>.json.
    ValueError when the ref names no figure, NotFound when it is not there."""
    at = parse(text)
    if at.path is None or not _is_view(at.path):
        raise ValueError(f"{text} names no figure: its path is views/<name>.json")
    if at.scheme == "run":
        return _view(read_artifact(at.name, at.path), at.path)
    try:
        path = inside(experiment_folder(at.name), *at.path.split("/"))
    except FileNotFoundError as exc:
        raise NotFound(str(exc)) from exc
    if not path.is_file():
        raise NotFound(f"experiment {at.name} has no {at.path}")
    return _view(path.read_bytes(), at.path)


def _items(view: View) -> ItemSource | None:
    """The items a figure's marks stand for, for the kinds that can say."""
    return view.items if isinstance(view, VegaView | PlotlyView) else None


def _is_view(path: str) -> bool:
    return path.startswith("views/") and path.endswith(".json")


def _view(data: bytes, path: str) -> View:
    try:
        return _VIEW.validate_json(data)
    except ValidationError as exc:
        raise ValueError(f"{path} is not a figure: {exc}") from exc


def _figure(at: str, view: View) -> TraceStep:
    return TraceStep(ref=at, what="figure", title=view.title)


def _made_by(run_id: str, path: str | None, artifacts: list[str]) -> list[TraceStep]:
    """The derive script that made a figure or derived file, with its commit: the script whose
    meta names this file as its output. None for a file the run logged or an agent added."""
    if path is None or not (_is_view(path) or path.startswith(f"{DERIVED}/")):
        return []
    name = PurePosixPath(path).stem
    script = f"{DERIVED}/{name}.py"
    if script not in artifacts:
        return []
    meta = json.loads(read_artifact(run_id, f"{DERIVED}/{name}.meta.json"))
    if meta.get("output") != path:  # replaced since, by hand or by another script
        return []
    git = meta.get("git") or {}
    return [TraceStep(ref=ref("run", run_id, script), what="script", title=script,
                      commit=git.get("sha"), dirty=git.get("dirty"),
                      code=code(git.get("sha"), git.get("dirty"), meta.get("script")))]  # fmt: skip


def _folder_of(path: str | None) -> str | None:
    """The item folder a records file sits in; None for anything else (the run's only one)."""
    if path is None or not path.endswith((".jsonl", ".ndjson")) or path.startswith(DERIVED):
        return None
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _item(run_id: str, folder: str | None, item: str) -> TraceStep:
    """An item's record in each condition's file and in each derived file that holds it."""
    paths = [a.path for a in get_run(run_id).artifacts]
    found = {d: fs for d, fs in folders(paths).items() if d != DERIVED}
    if not found:
        raise ValueError(f"run {run_id} has no per-item records")
    if folder is None:
        if len(found) > 1:
            raise ValueError(f"run {run_id} has item folders {list(found)}: name one")
        folder = next(iter(found))
    if folder not in found:
        raise ValueError(f"run {run_id} has no item folder {folder!r}; there are {list(found)}")
    files = found[folder]
    tables = [read_rows(run_id, f) for f in files]
    key = join_key(tables)
    if key is None:
        raise ValueError(f"the files in {folder!r} share no field naming an item once in each")
    rows = {f: r for f, t in zip(files, tables, strict=True) for r in t
            if key in r and key_text(r[key]) == item}  # fmt: skip
    if not rows:
        raise ValueError(f"no item {item!r} in {folder or '(top level)'} of run {run_id}")
    # derived columns join on the records' key, as the Items tab joins them
    for path in sorted(p for p in paths if p.startswith(f"{DERIVED}/") and p.endswith(".jsonl")):
        for r in read_rows(run_id, path):
            if key in r and key_text(r[key]) == item:
                rows[path] = r
    return TraceStep(ref=ref("run", run_id, files[0], item), what="item",
                     title=f"item {item} in {folder or '(top level)'}", rows=rows)  # fmt: skip


def _run(run_id: str) -> TraceStep:
    run = get_run(run_id)
    found = run_code(run)
    return TraceStep(ref=ref("run", run_id), what="run",
                     title=f"{run.name}{f' in {run.experiment}' if run.experiment else ''}",
                     commit=found.commit if found else None, dirty=found.dirty if found else None,
                     code=found)  # fmt: skip


def run_code(run: RunDetail) -> Code | None:
    """The code a run ran, from its tags; None when it recorded no commit."""
    dirty = run.tags.get("louped.git_dirty")
    return code(run.tags.get("louped.git_sha"), None if dirty is None else dirty == "true",
                run.tags.get("louped.script"))  # fmt: skip


def code(commit: str | None, dirty: bool | None, path: str | None) -> Code | None:
    """A commit and file with their page on the forge of the project's git remote, and whether
    the commit is pushed there; None without a commit."""
    if not commit:
        return None
    root = top(base())
    # outside a git repository, or a tag that is no sha: the commit is all there is
    if root is None or not re.fullmatch(r"[0-9a-f]{7,64}", commit):
        return Code(commit=commit, dirty=dirty, path=path)
    branches = pushed_to(root, commit)
    remote = remote_url(root, branches)
    url = web_url(remote, commit, path) if remote else None
    return Code(commit=commit, dirty=dirty, path=path, url=url,
                pushed=None if branches is None else bool(branches))  # fmt: skip

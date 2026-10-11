"""Boards: dashboards an agent writes as data (louped.stores.types.BoardView), and the tables they
read. A board's table is inline rows or a ref to what louped already keeps:

    run:<id>/<path>            a run's JSONL, CSV or JSON file: objects, or {"rows": [...]}
    experiment:<name>/<path>   the same, from an experiment's folder
    metrics:<run id>           the run's metric history: key, step, value, timestamp
    runs: | runs:<experiment>  every run (of one experiment): id, name, kind, status, model,
                               created, and each metric as its own field

A board is kept where any figure is (a run's views/, an experiment's views/), or as a page of
its own: boards/<name>.json at the project's root, listed in the sidebar.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import re
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from louped.core.paths import NAME, experiment_folder, inside
from louped.core.project import base
from louped.core.refs import parse
from louped.stores.runs import NotFound, get_run, list_runs, read_artifact
from louped.stores.types import BoardFilter, BoardPanel, BoardView, View

#: Rows a table is cut to: a board draws in a browser.
MAX_ROWS = 20_000
#: The folder at the project's root that holds boards shown as their own pages.
DIR = "boards"
_VIEW: TypeAdapter[View] = TypeAdapter(View)
log = logging.getLogger(__name__)


class Table(BaseModel):
    rows: list[dict[str, Any]]
    #: Every field any row has, in the order they first appear.
    columns: list[str]
    #: Whether rows were cut to MAX_ROWS.
    truncated: bool = False


class TableCheck(BaseModel):
    name: str
    rows: int
    columns: list[str]
    error: str | None = None


class PanelCheck(BaseModel):
    id: str
    #: Rows it draws with every control at its default and nothing clicked.
    rows: int | None
    problems: list[str]


class BoardCheck(BaseModel):
    """What a board reads and draws, before anyone sees it: each table's rows and fields, and
    each panel's rows and the fields it names that its table does not have."""

    ok: bool
    tables: list[TableCheck]
    panels: list[PanelCheck]


class BoardPage(BaseModel):
    name: str
    title: str
    about: str | None
    section: str


def read_table(ref: str) -> Table:
    """The rows a board's ref names; ValueError saying what is wrong with it, NotFound when the
    run or file is not there."""
    scheme, _, rest = ref.partition(":")
    if scheme == "metrics":
        run = get_run(rest)
        rows: list[dict[str, Any]] = [
            {"key": key, "step": p.step, "value": p.value, "timestamp": p.timestamp}
            for key, points in run.history.items()
            for p in points
        ]
    elif scheme == "runs":
        rows = [
            {
                "id": r.id,
                "name": r.name,
                "kind": r.kind,
                "experiment": r.experiment,
                "status": r.status,
                "model": r.model,
                "created": r.created.isoformat() if r.created else None,
                **r.metrics,
            }
            for r in list_runs()
            if not rest or r.experiment == rest
        ]
    else:
        at = parse(ref)
        if at.path is None or at.item is not None:
            raise ValueError(f"{ref} names no file: run:<id>/<path> or experiment:<name>/<path>")
        if at.scheme == "run":
            data = read_artifact(at.name, at.path)
        else:
            try:
                path = inside(experiment_folder(at.name), *at.path.split("/"))
            except FileNotFoundError as exc:
                raise NotFound(str(exc)) from exc
            if not path.is_file():
                raise NotFound(f"experiment {at.name} has no {at.path}")
            data = path.read_bytes()
        rows = parse_rows(data, at.path)
    return _table(rows)


def parse_rows(data: bytes, path: str) -> list[dict[str, Any]]:
    text = data.decode("utf-8")
    suffix = path.rsplit(".", 1)[-1].lower()
    if suffix in ("jsonl", "ndjson"):
        rows = []
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path} line {i} is not JSON: {exc}") from exc
    elif suffix in ("csv", "tsv"):
        dialect = "excel-tab" if suffix == "tsv" else "excel"
        rows = [{k: _cell(v) for k, v in r.items()}
                for r in csv.DictReader(io.StringIO(text), dialect=dialect)]  # fmt: skip
    elif suffix == "json":
        found = json.loads(text)
        rows = found.get("rows") if isinstance(found, dict) else found
    else:
        raise ValueError(f"{path}: a board reads JSONL, CSV, TSV or JSON files")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError(f'{path} is not a list of objects (or {{"rows": [...]}})')
    return rows


def _cell(v: str | None) -> Any:
    """A CSV cell as a number when it reads as one: a chart's axis needs numbers."""
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except ValueError:
        return v
    return int(n) if n.is_integer() and re.fullmatch(r"-?\d+", v.strip()) else n


def _table(rows: list[dict[str, Any]]) -> Table:
    columns: dict[str, None] = {}
    for r in rows[:MAX_ROWS]:
        columns.update(dict.fromkeys(r))
    return Table(rows=rows[:MAX_ROWS], columns=list(columns), truncated=len(rows) > MAX_ROWS)


def keep(row: dict[str, Any], f: BoardFilter, params: dict[str, Any]) -> bool:
    """Whether a row passes a filter; a param that is not set (none, "", []) passes all. Values
    compare as text the way JavaScript writes them, lowercased: a select's param is text, the
    field may be a number. apps/web/src/components/board.tsx filters the same way."""
    want = params.get(f.param) if f.param is not None else f.value
    if want is None or want == "" or want == []:
        return True
    got = row.get(f.field)
    if f.op == "in":
        return _text(got) in [_text(w) for w in (want if isinstance(want, list) else [want])]
    if f.op == "contains":
        return (_text(want) or "") in (_text(got) or "")
    if isinstance(want, list):
        return False
    if f.op in ("==", "!="):
        return (_text(got) == _text(want)) == (f.op == "==")
    a, b = _number(got), _number(want)
    if a is None or b is None:
        return False
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[f.op]


def _text(v: Any) -> str | None:
    """A value as JavaScript's String() writes it, lowercased: 2.0 is "2", True is "true"."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, list):
        return ",".join(_text(x) or "" for x in v)
    return str(v).lower()


def _number(v: Any) -> float | None:
    """A finite number, from a number or its text; not a yes/no."""
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def check(board: BoardView) -> BoardCheck:
    """Reads every table of a board and tries every panel on it, as the app would draw it before
    anyone clicks."""
    tables: dict[str, Table | None] = {}
    found: list[TableCheck] = []
    for name, data in board.data.items():
        try:
            # inline rows are drawn whole, so they are checked whole
            table = (Table(rows=data.rows, columns=_table(data.rows).columns)
                     if data.rows is not None else read_table(data.ref or ""))  # fmt: skip
        except (ValueError, NotFound, OSError) as exc:
            tables[name] = None
            found.append(TableCheck(name=name, rows=0, columns=[], error=str(exc)))
            continue
        tables[name] = table
        found.append(TableCheck(name=name, rows=len(table.rows), columns=table.columns))
    params = {c.id: c.default for c in board.controls}
    problems: list[str] = []
    for c in board.controls:
        if c.data and c.field and (t := tables.get(c.data)) and c.field not in t.columns:
            problems.append(f"control {c.id}: {c.data} has no field {c.field}")
        if not c.about:
            problems.append(f"control {c.id} has no about: say what it does")
    panels = [_panel(p, tables, params) for p in board.panels]
    ok = (
        not problems and all(t.error is None for t in found) and not any(p.problems for p in panels)
    )
    if problems:  # the controls' problems, said once, on the first panel
        panels[0].problems[:0] = problems
    return BoardCheck(ok=ok, tables=found, panels=panels)


def _panel(p: BoardPanel, tables: dict[str, Table | None], params: dict[str, Any]) -> PanelCheck:
    told = [] if p.about or p.kind == "text" else ["no about: say how to read it"]
    if p.data is None:
        return PanelCheck(id=p.id, rows=None, problems=told)
    table = tables.get(p.data)
    if table is None:
        return PanelCheck(id=p.id, rows=None, problems=[f"its table {p.data} could not be read"])
    named = [*(f.field for f in p.where), *([p.select.field] if p.select else []),
             *(getattr(p, k) for k in ("x", "y", "z", "color", "text", "size", "frame", "sort",
                                       "field", "node", "label") if getattr(p, k)),
             *(p.columns or [])]  # fmt: skip
    problems = [f"{p.data} has no field {f}" for f in dict.fromkeys(named)
                if f not in table.columns]  # fmt: skip
    if p.kind == "diagram" and p.edges and (edges := tables.get(p.edges)):
        problems += [f"{p.edges} has no field {f}" for f in (p.source, p.target)
                     if f and f not in edges.columns]  # fmt: skip
    rows = [r for r in table.rows if all(keep(r, f, params) for f in p.where)]
    return PanelCheck(id=p.id, rows=len(rows), problems=told + problems)


def list_boards() -> list[BoardPage]:
    """The boards shown as their own pages; a file that is not a board is skipped."""
    folder = base() / DIR
    out = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            view = _VIEW.validate_json(path.read_bytes())
        except ValidationError as exc:  # its page says why; the sidebar lists the rest
            log.warning("skipping board %s: %s", path, exc)
            continue
        if isinstance(view, BoardView):
            out.append(BoardPage(name=path.stem, title=view.title, about=view.about,
                                 section=view.section))  # fmt: skip
    return out


def get_board(name: str) -> BoardView:
    """boards/<name>.json; NotFound when there is none, ValueError saying why it is not a board."""
    path = inside(base() / DIR, _named(name))
    if not path.is_file():
        raise NotFound(f"{DIR}/{path.name}")
    try:
        view = _VIEW.validate_json(path.read_bytes())
    except ValidationError as exc:
        raise ValueError(f"{DIR}/{path.name} is not a board: {exc}") from exc
    if not isinstance(view, BoardView):
        raise ValueError(f"{DIR}/{path.name} is a {view.kind} figure, not a board")
    return view


def save_board(name: str, board: BoardView) -> BoardPage:
    """Writes boards/<name>.json, replacing one of that name."""
    path = inside(base() / DIR, _named(name))
    path.parent.mkdir(exist_ok=True)
    data = board.model_dump(mode="json", exclude_none=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return BoardPage(name=name, title=board.title, about=board.about, section=board.section)


def _named(name: str) -> str:
    if not NAME.match(name):
        raise ValueError(f"{name!r} is not a board name: lowercase letters, digits and -")
    return f"{name}.json"

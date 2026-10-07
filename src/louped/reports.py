"""reports/: what the project hands to people. Markdown write-ups, slide decks and Word documents
the agent writes (with python-pptx and python-docx), and figures exported from runs.

An exported figure has a sidecar, <file>.refs.json, holding the ref it was exported from and the
trace of that ref at the time: the run, the script and the commit behind it. A deck or a document
carries its refs in its text (a slide's speaker notes count), where louped check reads them.

Reports are grouped by the experiment they report on (Report.experiment). A Markdown report can
also carry live refs, which the app fills in when it renders the file, so the file stays plain
Markdown and its numbers never go stale:

    {{run:<id> <metric>}}             the metric's latest value, to three significant decimals
    {{run:<id> <metric> :.1%}}        the value in a Python format spec
    {{<ref to a figure>}}             the figure (run:<id>/views/<name>.json, experiment:...)
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from louped.core import documents
from louped.core.paths import experiment_folder, experiments_dir, home, inside
from louped.core.refs import IN_TEXT, parse
from louped.stores import NotFound, get_run, list_runs, read_view, trace
from louped.stores.types import PlotlyView, VegaView, View

Kind = Literal["md", "pptx", "docx", "pdf", "svg", "png"]
KINDS: dict[str, Kind] = {".md": "md", ".pptx": "pptx", ".docx": "docx", ".pdf": "pdf",
                          ".svg": "svg", ".png": "png"}  # fmt: skip
Format = Literal["svg", "png", "pdf"]
REFS = ".refs.json"
#: Where an exported figure goes in reports/.
FIGURES = "figures"
#: A live ref in Markdown, what is between the braces as its group.
LIVE = re.compile(r"\{\{[ \t]*((?:run|experiment):[^{}\n]*?)[ \t]*\}\}")
_FRONT = re.compile(r"\A---\n(.*?)\n---\s*$", re.S | re.M)


class Report(BaseModel):
    #: Relative to reports/.
    path: str
    kind: Kind
    size: int
    modified: datetime
    #: For an exported figure, the ref it was exported from.
    ref: str | None = None
    #: The experiment it reports on: a Markdown report's front matter `experiment:`, else its
    #: first folder under reports/ when that is an experiment, else the one experiment all its
    #: refs point to; None when none of these names one.
    experiment: str | None = None
    #: The runs its refs (and an exported figure's ref) cite, in the order they first appear.
    runs: list[str] = []


class Live(BaseModel):
    """A live ref resolved: a run's metric as text, or a figure; else why it does not resolve."""

    #: As written between the braces.
    text: str
    #: The run or figure it points at.
    ref: str
    metric: str | None = None
    #: The metric's value, formatted.
    value: str | None = None
    view: View | None = None
    error: str | None = None


class MissingTool(RuntimeError):
    """A program louped calls but does not install, such as LibreOffice."""


#: One LibreOffice conversion at a time: they share a profile, which LibreOffice locks.
_DRAWING = threading.Lock()


def reports_dir() -> Path:
    """reports/ at the project's root, beside experiments/ and sources/."""
    return experiments_dir().parent / "reports"


def list_reports() -> list[Report]:
    """Every file in reports/ louped shows, by path, with the experiment it reports on and the
    runs it cites."""
    root = reports_dir()
    if not root.is_dir():
        return []
    reports = [_report(root, f) for f in sorted(root.rglob("*")) if f.is_file() and shown(f)]
    owners: dict[str, str | None] | None = None  # run id -> experiment, read once when needed
    for r in reports:
        named, refs = _cited(root / r.path)
        refs = [r.ref, *refs] if r.ref else refs
        r.runs = list(dict.fromkeys(_run_of(x) for x in refs if x.startswith("run:")))
        r.experiment = named or _folder_experiment(r.path)
        if r.experiment is None and refs:
            if owners is None and r.runs:
                owners = {run.id: run.experiment for run in list_runs()}
            found = {_experiment_of(x, owners or {}) for x in refs}
            r.experiment = found.pop() if len(found) == 1 else None
    return reports


def _run_of(ref: str) -> str:
    return re.split(r"[/#]", ref.removeprefix("run:"), maxsplit=1)[0]


def _experiment_of(ref: str, owners: dict[str, str | None]) -> str | None:
    """The experiment a ref points to: an experiment's own, or its run's; None for a run not
    filed under one, or not there."""
    if ref.startswith("experiment:"):
        return re.split(r"[/#]", ref.removeprefix("experiment:"), maxsplit=1)[0]
    return owners.get(_run_of(ref))


def _folder_experiment(path: str) -> str | None:
    """The first folder of a path under reports/ when an experiment has that name."""
    parts = path.split("/")
    if len(parts) < 2:
        return None
    try:
        experiment_folder(parts[0])
    except (FileNotFoundError, ValueError):
        return None
    return parts[0]


#: What each file names and cites, by path, kept while its size and time are the same: a deck is
#: read again only once it changes.
_CITED: dict[Path, tuple[tuple[int, int], tuple[str | None, list[str]]]] = {}


def _cited(file: Path) -> tuple[str | None, list[str]]:
    """The experiment a Markdown file's front matter names, and every ref in a file's text. A
    file that cannot be read cites nothing here; louped check names it."""
    stat = file.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    if (kept := _CITED.get(file)) and kept[0] == key:
        return kept[1]
    named = None
    try:
        match KINDS[file.suffix.lower()]:
            case "md":
                text = file.read_text(encoding="utf-8")
                if front := _FRONT.match(text):
                    fields = dict(line.split(":", 1) for line in front.group(1).splitlines()
                                  if ":" in line)  # fmt: skip
                    named = fields.get("experiment", "").strip() or None
            case "pptx":
                text = "\n".join(documents.pptx_slides(file)[0])
            case "docx":
                text = "\n".join(b.text for b in documents.docx_blocks(file)[0])
            case _:
                text = ""
    except Exception:
        text = ""
    found = (named, list(dict.fromkeys(m.group(0).rstrip(".:") for m in IN_TEXT.finditer(text))))
    _CITED[file] = (key, found)
    return found


def shown(file: Path) -> bool:
    """Whether louped shows a file: one of its kinds, and not the lock file Office keeps beside
    an open one (~$deck.pptx)."""
    return file.suffix.lower() in KINDS and not file.name.startswith("~$")


def report_file(path: str) -> Path:
    """A file in reports/ by its path there; ValueError for a path out of it or a kind louped
    does not show, FileNotFoundError when there is none."""
    file = inside(reports_dir(), *path.split("/"))
    if not shown(file):
        raise ValueError(f"{path}: louped shows {', '.join(sorted(KINDS))} files")
    if not file.is_file():
        raise FileNotFoundError(f"no report {path}")
    return file


def outline(path: str) -> list[str]:
    """A deck's text slide by slide, a document's paragraph by paragraph (a table as one), or a
    Markdown file whole."""
    file = report_file(path)
    match KINDS[file.suffix.lower()]:
        case "pptx":
            return documents.pptx_slides(file)[0]
        case "docx":
            return [b.text for b in documents.docx_blocks(file)[0]]
        case "md":
            return [file.read_text(encoding="utf-8")]
        case kind:
            raise ValueError(f"{path} is a {kind}: it has no text outline")


def resolve(texts: list[str]) -> list[Live]:
    """Live refs, each as written between the braces, resolved: a run's metric to its latest
    value, a figure's ref to the figure. One that does not resolve says why in its error."""
    run = functools.cache(get_run)
    out: list[Live] = []
    for text in texts:
        words = text.split()
        live = Live(text=text, ref=words[0] if words else "")
        try:
            ref, metric, spec = _live_parts(words)
            live.metric = metric
            if metric is None:
                live.view = read_view(ref)
            else:
                at = parse(ref)
                if at.scheme != "run" or at.path or at.item:
                    raise ValueError(f"{ref} is not a run: a metric is read from run:<id>")
                metrics = run(at.name).metrics
                if metric not in metrics:
                    raise ValueError(f"run {at.name} has no metric {metric}; it has "
                                     f"{', '.join(sorted(metrics)[:12]) or 'none'}")  # fmt: skip
                live.value = number(metrics[metric], spec)
        except NotFound as exc:
            live.error = f"not found: {exc.args[0] if exc.args else live.ref}"
        except ValueError as exc:
            live.error = str(exc)
        out.append(live)
    return out


def _live_parts(words: list[str]) -> tuple[str, str | None, str | None]:
    """A live ref's ref, metric and format spec."""
    spec = words.pop()[1:] if len(words) > 1 and words[-1].startswith(":") else None
    if len(words) not in (1, 2):
        raise ValueError("a live ref is {{run:<id> <metric>}}, {{run:<id> <metric> :<format>}} "
                         "or {{<ref to a figure>}}")  # fmt: skip
    if spec is not None and len(words) == 1:
        raise ValueError("a format is for a metric: {{run:<id> <metric> :<format>}}")
    return words[0], words[1] if len(words) == 2 else None, spec


def number(value: float, spec: str | None = None) -> str:
    """A metric as text: in the format spec when given (.1%, .2f), else to three significant
    decimals with no trailing zeros (0.912, 0.0912, 1234.568, 3)."""
    if spec is not None:
        try:
            return format(value, spec)
        except ValueError as exc:
            raise ValueError(f"{spec!r} is not a format for a number: {exc}") from exc
    if not math.isfinite(value):
        return str(value)
    if value == int(value):
        return str(int(value))
    places = max(3, 2 - math.floor(math.log10(abs(value))))
    return f"{value:.{places}f}".rstrip("0").rstrip(".")


def render(text: str) -> tuple[str, list[Live]]:
    """Markdown with each live metric replaced by its value; figures stay as written. Returns the
    text and the live refs that do not resolve, which also stay as written."""
    resolved = {r.text: r for r in resolve(list(dict.fromkeys(LIVE.findall(text))))}

    def value(m: re.Match[str]) -> str:
        return resolved[m.group(1)].value or m.group(0)

    return LIVE.sub(value, text), [r for r in resolved.values() if r.error]


def preview_pdf(path: str) -> Path:
    """A deck or document as a PDF, made by LibreOffice and kept by the file's hash. MissingTool
    when LibreOffice is not installed."""
    file = report_file(path)
    if KINDS[file.suffix.lower()] not in ("pptx", "docx"):
        raise ValueError(f"{path} is not a deck or a document")
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if office is None:
        raise MissingTool("LibreOffice is not installed, so louped cannot draw this file: "
                          "install it from libreoffice.org to see it as it prints")  # fmt: skip
    sha = hashlib.sha256(file.read_bytes()).hexdigest()
    out = home() / "previews" / sha
    pdf = out / f"{file.stem}.pdf"
    if pdf.is_file():
        return pdf
    out.mkdir(parents=True, exist_ok=True)
    profile = (home() / "previews" / "profile").as_uri()  # its own, beside a running LibreOffice
    convert = [office, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
               "--outdir", str(out), str(file)]  # fmt: skip
    with _DRAWING:
        try:
            done = subprocess.run(convert, capture_output=True, text=True, timeout=180, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"LibreOffice took over {exc.timeout:.0f}s to convert {path}"
            ) from exc
    if done.returncode != 0 or not pdf.is_file():
        raise RuntimeError(f"LibreOffice could not convert {path}: {done.stderr.strip()}")
    return pdf


def export_figure(
    ref: str, fmt: Format = "svg", name: str | None = None, replace: bool = False
) -> Report:
    """Export a run's or experiment's figure to reports/figures/<name>.<fmt>, with a sidecar
    holding its ref and trace. Vega-Lite figures export through vl-convert; Plotly figures
    through Kaleido, which needs Chrome. The kinds the app draws itself do not export.
    FileExistsError when the file is there and replace is not set: a deck may show it."""
    view = read_view(ref)
    if isinstance(view, VegaView):
        data = _vega(view, fmt)
    elif isinstance(view, PlotlyView):
        data = _plotly(view, fmt)
    else:
        raise ValueError(f"{ref} is a {view.kind} figure, which only the app draws: "
                         "export a vega or plotly figure")  # fmt: skip
    at = parse(ref)
    name = name or f"{at.name}-{Path(at.path or '').stem}"
    if not re.fullmatch(r"[A-Za-z0-9][\w.-]{0,99}", name):
        raise ValueError(f"{name!r} is not a file name: letters, digits, '.', '_' and '-'")
    target = inside(reports_dir(), FIGURES, f"{name}.{fmt}")
    if target.exists() and not replace:
        raise FileExistsError(f"reports/{FIGURES}/{target.name} exists: replace it, or give a name")
    target.parent.mkdir(parents=True, exist_ok=True)
    meta = {"ref": ref, "exported": datetime.now(UTC).isoformat(),
            "trace": trace(ref).model_dump(mode="json")}  # fmt: skip
    _write(target, data)
    _write(_sidecar(target), (json.dumps(meta, indent=2) + "\n").encode())
    return _report(reports_dir(), target)


def _vega(view: VegaView, fmt: Format) -> bytes:
    import vl_convert as vlc

    spec = {"title": view.title, **view.spec}
    if fmt == "svg":
        return vlc.vegalite_to_svg(spec).encode()
    return vlc.vegalite_to_png(spec, scale=2) if fmt == "png" else vlc.vegalite_to_pdf(spec)


def _plotly(view: PlotlyView, fmt: Format) -> bytes:
    import plotly.io as pio
    from kaleido.errors import ChromeNotFoundError

    figure = {"data": view.data, "layout": {"title": {"text": view.title}, **view.layout}}
    try:
        return pio.to_image(figure, format=fmt)
    except RuntimeError as exc:  # Plotly raises its own error in place of Kaleido's
        if isinstance(exc.__context__, ChromeNotFoundError):
            raise MissingTool("Plotly exports figures through Chrome, which is not installed: "
                              "install Chrome, or run plotly_get_chrome") from exc  # fmt: skip
        raise


def sidecar_ref(sidecar: Path) -> str:
    """The ref an exported figure's sidecar holds; ValueError naming the file when it holds
    none."""
    try:
        ref = json.loads(sidecar.read_text(encoding="utf-8"))["ref"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{sidecar.name} is not a figure's refs file: {exc}") from exc
    if not isinstance(ref, str):
        raise ValueError(f"{sidecar.name} is not a figure's refs file: its ref is not text")
    return ref


def _report(root: Path, file: Path) -> Report:
    sidecar = _sidecar(file)
    ref = sidecar_ref(sidecar) if sidecar.is_file() else None
    stat = file.stat()
    return Report(path=file.relative_to(root).as_posix(), kind=KINDS[file.suffix.lower()],
                  size=stat.st_size, modified=datetime.fromtimestamp(stat.st_mtime, UTC),
                  ref=ref)  # fmt: skip


def _sidecar(file: Path) -> Path:
    return file.with_name(file.name + REFS)


def _write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)

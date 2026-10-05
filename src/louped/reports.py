"""reports/: what the project hands to people. Markdown write-ups, slide decks and Word documents
the agent writes (with python-pptx and python-docx), and figures exported from runs.

An exported figure has a sidecar, <file>.refs.json, holding the ref it was exported from and the
trace of that ref at the time: the run, the script and the commit behind it. A deck or a document
carries its refs in its text (a slide's speaker notes count), where louped check reads them.
"""

from __future__ import annotations

import hashlib
import json
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
from louped.core.paths import experiments_dir, home, inside
from louped.core.refs import parse
from louped.stores import read_view, trace
from louped.stores.types import PlotlyView, VegaView

Kind = Literal["md", "pptx", "docx", "pdf", "svg", "png"]
KINDS: dict[str, Kind] = {".md": "md", ".pptx": "pptx", ".docx": "docx", ".pdf": "pdf",
                          ".svg": "svg", ".png": "png"}  # fmt: skip
Format = Literal["svg", "png", "pdf"]
REFS = ".refs.json"
#: Where an exported figure goes in reports/.
FIGURES = "figures"


class Report(BaseModel):
    #: Relative to reports/.
    path: str
    kind: Kind
    size: int
    modified: datetime
    #: For an exported figure, the ref it was exported from.
    ref: str | None = None


class MissingTool(RuntimeError):
    """A program louped calls but does not install, such as LibreOffice."""


#: One LibreOffice conversion at a time: they share a profile, which LibreOffice locks.
_DRAWING = threading.Lock()


def reports_dir() -> Path:
    """reports/ at the project's root, beside experiments/ and sources/."""
    return experiments_dir().parent / "reports"


def list_reports() -> list[Report]:
    """Every file in reports/ louped shows, by path."""
    root = reports_dir()
    if not root.is_dir():
        return []
    return [_report(root, f) for f in sorted(root.rglob("*")) if f.is_file() and shown(f)]


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

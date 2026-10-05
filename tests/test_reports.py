"""reports/: decks, documents and exported figures, shown, previewed and checked."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.util import Inches
from test_agent import call, tools
from test_views import CLOUD, run_id  # noqa: F401  (the fixture)

from louped.check import check
from louped.reports import Format, MissingTool, export_figure, list_reports, outline, preview_pdf
from louped.server import create_app
from louped.stores import add_view
from louped.stores.types import PlotlyView, VegaView

BARS = {"kind": "vega", "title": "Caving by condition",
        "spec": {"mark": "bar", "data": {"values": [{"c": "pressure", "v": 0.9}]},
                 "encoding": {"x": {"field": "c", "type": "nominal"},
                              "y": {"field": "v", "type": "quantitative"}}}}  # fmt: skip
#: A Chrome for Kaleido, where the tests run in one; Plotly export is checked only there.
CHROME = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def deck(path: Path, run: str) -> None:
    """A deck of two slides: a number sourced in the speaker notes, and one that is not."""
    slides = Presentation()
    first = slides.slides.add_slide(slides.slide_layouts[5])
    assert first.shapes.title is not None
    first.shapes.title.text = "Caving rate 0.92"
    first.notes_slide.notes_text_frame.text = f"Source: run:{run}"  # type: ignore[union-attr]
    second = slides.slides.add_slide(slides.slide_layouts[6])
    second.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame.text = "78%"
    slides.save(str(path))


def doc(path: Path, run: str) -> None:
    """A document whose table takes its source from the paragraph above it."""
    d = Document()
    d.add_paragraph(f"Caving by condition, run:{run}.")
    table = d.add_table(rows=2, cols=2)
    for row, (a, b) in zip(table.rows, (("condition", "caved"), ("pressure", "0.92")), strict=True):
        row.cells[0].text, row.cells[1].text = a, b
    d.add_paragraph("Unsourced: 0.5.")
    d.save(str(path))


def test_decks_and_documents_are_listed_outlined_and_checked(
    run_id: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    assert list_reports() == []
    root = tmp_path / "reports"
    root.mkdir()
    deck(root / "lab.pptx", run_id)
    doc(root / "memo.docx", run_id)
    (root / "notes.txt").write_text("not shown")
    assert [(r.path, r.kind) for r in list_reports()] == [
        ("lab.pptx", "pptx"),
        ("memo.docx", "docx"),
    ]
    assert outline("lab.pptx") == [f"Caving rate 0.92\nSource: run:{run_id}", "78%"]
    assert outline("memo.docx")[1] == "condition | caved\npressure | 0.92"
    with pytest.raises(ValueError, match="louped shows"):
        outline("notes.txt")
    with pytest.raises(ValueError, match="not a name under"):
        outline("../experiments/x.md")
    got = [(i.where(), i.message.split(" has")[0]) for i in check()]
    assert got == [("reports/lab.pptx slide 2", "78%"), ("reports/memo.docx paragraph 3", "0.5")]


def test_a_vega_figure_exports_with_its_ref_and_trace(
    run_id: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    add_view(run_id, "bars", VegaView.model_validate(BARS))
    ref = f"run:{run_id}/views/bars.json"
    formats: tuple[tuple[Format, bytes], ...] = (("svg", b"<svg"), ("png", b"\x89PNG"),
                                                 ("pdf", b"%PDF"))  # fmt: skip
    for fmt, head in formats:
        made = export_figure(ref, fmt, name="bars")
        assert (made.path, made.kind, made.ref) == (f"figures/bars.{fmt}", fmt, ref)
        assert (tmp_path / "reports" / made.path).read_bytes().startswith(head)
    assert [(r.path, r.ref) for r in list_reports()] == [
        (f"figures/bars.{fmt}", ref) for fmt in ("pdf", "png", "svg")
    ]
    sidecar_file = tmp_path / "reports" / "figures" / "bars.svg.refs.json"
    sidecar = json.loads(sidecar_file.read_text())
    assert sidecar["ref"] == ref and sidecar["trace"]["steps"][-1]["what"] == "run"
    with pytest.raises(ValueError, match="names no figure"):
        export_figure(f"run:{run_id}")
    with pytest.raises(ValueError, match="not a file name"):
        export_figure(ref, name="../x")
    assert check() == []
    # an exported figure whose run is gone no longer checks
    sidecar["ref"] = "run:m-gone/views/bars.json"
    sidecar_file.write_text(json.dumps(sidecar))
    [gone] = check()
    assert gone.file == "reports/figures/bars.svg.refs.json" and "does not resolve" in gone.message


@pytest.mark.skipif(not CHROME.is_file(), reason="Kaleido needs Chrome")
def test_a_plotly_figure_exports_through_kaleido(
    run_id: str,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BROWSER_PATH", str(CHROME))
    add_view(run_id, "cloud", PlotlyView.model_validate(CLOUD))
    made = export_figure(f"run:{run_id}/views/cloud.json", "png")
    assert made.path == f"figures/{run_id}-cloud.png"
    assert (tmp_path / "reports" / made.path).read_bytes().startswith(b"\x89PNG")


def converts(folder: Path) -> bool:
    """Whether a LibreOffice here can make a PDF: some installs carry only its core."""
    office = shutil.which("soffice")
    if office is None:
        return False
    (folder / "t.txt").write_text("x")
    convert = [office, "--headless", "--convert-to", "pdf", "--outdir", str(folder)]
    subprocess.run([*convert, str(folder / "t.txt")], capture_output=True, timeout=120, check=False)
    return (folder / "t.pdf").is_file()


@pytest.mark.skipif(not converts(Path(tempfile.mkdtemp())), reason="no LibreOffice that converts")
def test_a_deck_previews_as_a_pdf_through_libreoffice(
    run_id: str,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "reports").mkdir()
    deck(tmp_path / "reports" / "lab.pptx", run_id)
    pdf = preview_pdf("lab.pptx")
    assert pdf.read_bytes().startswith(b"%PDF") and preview_pdf("lab.pptx") == pdf  # kept
    monkeypatch.setenv("PATH", str(tmp_path))  # no LibreOffice on it
    (tmp_path / "reports" / "lab.pptx").write_bytes(b"changed")
    with pytest.raises(MissingTool, match="LibreOffice is not installed"):
        preview_pdf("lab.pptx")


def test_reports_through_the_api_and_mcp(
    run_id: str,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_view(run_id, "bars", VegaView.model_validate(BARS))
    mcp = tools()
    made = call(mcp, "export_figure", ref=f"run:{run_id}/views/bars.json")
    assert made["path"] == f"figures/{run_id}-bars.svg"
    assert [r["path"] for r in call(mcp, "reports")] == [made["path"]]
    api = TestClient(create_app(launching=True), base_url="http://localhost")
    assert api.get("/api/reports/file", params={"path": made["path"]}).text.startswith("<svg")
    assert api.get("/api/reports/file", params={"path": "figures/none.svg"}).status_code == 404
    assert api.get("/api/reports/outline", params={"path": made["path"]}).status_code == 400
    deck(tmp_path / "reports" / "lab.pptx", run_id)
    monkeypatch.setenv("PATH", str(tmp_path))
    missing = api.get("/api/reports/preview", params={"path": "lab.pptx"})
    assert missing.status_code == 501 and "LibreOffice" in missing.json()["detail"]
    nope = api.post("/api/reports/figures", json={"ref": f"run:{run_id}/views/none.json"})
    assert nope.status_code == 404
    readonly = TestClient(create_app(launching=False), base_url="http://localhost")
    assert readonly.post("/api/reports/figures", json={"ref": "x"}).status_code == 403

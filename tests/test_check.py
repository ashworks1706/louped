"""louped check: result numbers beside their source, citations on pinned pages, refs that
resolve, pins still on their pages."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_agent import call, tools
from test_sources import pdf
from test_stores import write_experiment
from test_views import run_id  # noqa: F401  (the fixture)

from louped.check import CODE, NUMBER, _units, check
from louped.server import create_app
from louped.sources import add_pin, add_source

GROUNDED = """# pressure

## Result

The model changed its answer on 12/40 items (30%), run:{run}/raw/pressure.jsonl.

- Evidence brings it back to 0.78 [@paper p1].

Caving rate by condition, `run:{run}`:

| condition | caved |
|---|---|
| pressure | 0.92 |
| evidence | 0.22 |
"""


def test_units_are_paragraphs_items_and_captioned_tables_never_code_or_headings() -> None:
    text = "---\nx: 0.5\n---\n# 1.5\n\na 0.1\nb\n\n- c\n- d\n```\n0.2\n```\nt\n\n|a|\n|b|\n"
    assert [[n for n, _ in u] for u in _units(text)] == [[6, 7], [9], [10], [14, 16, 17]]
    # a table after a list or a heading stands alone
    assert [[n for n, _ in u] for u in _units("- a\n\n|b|\n# h\n|c|\n")] == [[1], [3], [5]]


def test_a_grounded_write_up_passes_and_each_gap_is_named(
    run_id: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    write_experiment(tmp_path, "pressure", "honesty", "active")
    (tmp_path / "paper.pdf").write_bytes(pdf("Models cave to pushback"))
    add_source(str(tmp_path / "paper.pdf"), key="paper")
    add_pin("paper", 1, "cave to pushback")
    readme = tmp_path / "experiments" / "pressure" / "README.md"
    readme.write_text(GROUNDED.format(run=run_id))
    assert check() == []

    readme.write_text(
        "# pressure\n\n"
        "It caved 78% of the time on Llama-3.1-8B, over 3 seeds in 2026.\n\n"  # 78% unsourced
        "Prior work agrees [@paper p2] and [@nope p1] and [@paper].\n\n"
        "See run:m-404 and experiment:missing, and `0.5` in code.\n"
    )
    (tmp_path / "sources" / "pins.jsonl").write_text(
        (tmp_path / "sources" / "pins.jsonl").read_text().replace("cave to pushback", "gone")
    )
    got = [(i.file, i.line, i.kind) for i in check()]
    assert got == [
        ("experiments/pressure/README.md", 3, "number"),
        ("experiments/pressure/README.md", 5, "citation"),
        ("experiments/pressure/README.md", 5, "citation"),
        ("experiments/pressure/README.md", 5, "citation"),
        ("experiments/pressure/README.md", 7, "ref"),
        ("experiments/pressure/README.md", 7, "ref"),
        ("sources/pins.jsonl", 1, "pin"),
    ]
    messages = [i.message for i in check()]
    assert messages[0].startswith("78% has no source beside it")
    assert "has pages 1 to 1" in messages[1] and "names no source" in messages[2]
    assert "names no page" in messages[3]
    assert "is no longer on page 1 of paper" in messages[6]


def test_check_through_the_api_and_mcp(run_id: str, tmp_path: Path) -> None:  # noqa: F811
    write_experiment(tmp_path, "pressure", "honesty", "active")
    (tmp_path / "experiments" / "pressure" / "notes.md").write_text("Up to 0.9.\n")
    [issue] = call(tools(), "check", path="experiments/pressure/notes.md")
    assert (issue["file"], issue["kind"]) == ("experiments/pressure/notes.md", "number")
    api = TestClient(create_app(), base_url="http://localhost")
    assert api.get("/api/check", params={"path": "/etc"}).status_code == 400
    assert api.get("/api/check", params={"path": "nope.md"}).status_code == 400
    assert json.loads(api.get("/api/check").text)[0]["line"] == 1


def numbers(text: str) -> list[str]:
    return [m.group(0) for m in NUMBER.finditer(text)]


def test_result_numbers_are_found_and_names_paths_and_versions_in_code_are_not() -> None:
    assert numbers("acc 0.92, Δ -3.2% (\u22120.12), +4.1%, 0.5-0.7, 12/40 and 1,234.5 tokens.") == [
        "0.92", "-3.2%", "\u22120.12", "+4.1%", "0.5", "12/40", "1,234.5",
    ]  # fmt: skip
    assert numbers("Llama-3.1-8B, GPT-4.1, v0.2, a/0.5/b, https://x.org/1.5, 3 seeds, 2026") == []
    # a version or a path is written in code, which is never checked
    assert numbers(CODE.sub("", "torch `2.1`, `python 3.11`")) == []


def test_units_skip_long_fences_indented_code_and_comments_and_keep_loose_items() -> None:
    text = "````\n```\n0.5\n````\nx\n\n    0.3 code\n\n<!-- 0.4\n-->\n- item\n\n  more 0.2\n"
    assert [[n for n, _ in u] for u in _units(text)] == [[5], [11, 13]]


def test_bad_citations_paths_outside_and_pin_lines_are_reported(tmp_path: Path) -> None:
    notes = tmp_path / "experiments" / "notes.md"
    notes.parent.mkdir()
    notes.write_text("Up to 0.9 [@Smith2024 p4], [@paper, p4].\n")
    assert [i.message.split(" is not")[0][:15] for i in check([notes])] == [
        "[@Smith2024 p4]", "[@paper, p4]", "0.9 has no sour",
    ]  # fmt: skip
    with pytest.raises(ValueError, match="not in the project"):
        check([Path("/etc/hostname")])
    (tmp_path / "paper.pdf").write_bytes(pdf("Models cave to pushback"))
    add_source(str(tmp_path / "paper.pdf"), key="paper")
    add_pin("paper", 1, "cave to pushback")
    pins = tmp_path / "sources" / "pins.jsonl"
    pins.write_text("\n" + pins.read_text().replace("cave to pushback", "gone"))
    [stale] = check([notes])[3:]
    assert (stale.file, stale.line) == ("sources/pins.jsonl", 2)

"""Boards: dashboards an agent writes as data, checked against the tables they read, kept as a
figure or as a page of their own."""

import asyncio
import json
from pathlib import Path

import mlflow
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from test_agent import call, tools
from test_stores import write_experiment

from louped.server import create_app
from louped.stores.boards import keep, read_table
from louped.stores.types import BoardFilter
from louped.tracking import start_run


@pytest.fixture
def run_id(tmp_path: Path) -> str:
    """A run with per-item records, a CSV and a metric history."""
    raw = tmp_path / "raw"
    raw.mkdir()
    rows = [{"qid": 1, "model": "base", "score": 0.2}, {"qid": 2, "model": "dpo", "score": 0.9},
            {"qid": 3, "model": "dpo", "score": 0.7}]  # fmt: skip
    (raw / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (raw / "steps.csv").write_text("step,loss,phase\n1,2.5,warm\n2,1.25,main\n")
    with start_run("q", name="r") as r:
        mlflow.log_artifacts(str(raw), "raw")
        for step, loss in enumerate([2.0, 1.0, 0.5]):
            mlflow.log_metric("loss", loss, step=step)
    return f"m-{r.info.run_id}"


def board(run_id: str) -> dict:
    return {
        "kind": "board",
        "title": "Scores by model",
        "about": "Pick a model; the table and the stat follow.",
        "data": {
            "items": {"ref": f"run:{run_id}/raw/items.jsonl"},
            "loss": {"ref": f"metrics:{run_id}", "live": 5},
            "graph": {"rows": [{"id": "data"}, {"id": "train"}]},
            "links": {"rows": [{"from": "data", "to": "train"}]},
        },
        "controls": [
            {
                "id": "model",
                "kind": "select",
                "data": "items",
                "field": "model",
                "default": "dpo",
                "about": "Which model's items.",
            }
        ],
        "panels": [
            {
                "id": "chart",
                "about": "How to read it.",
                "kind": "vega",
                "data": "items",
                "select": {"param": "qid", "field": "qid"},
                "spec": {
                    "mark": "bar",
                    "encoding": {
                        "x": {"field": "qid"},
                        "y": {"field": "score", "type": "quantitative"},
                    },
                },
            },
            {
                "id": "rows",
                "about": "How to read it.",
                "kind": "table",
                "data": "items",
                "where": [{"field": "model", "param": "model"}],
            },
            {
                "id": "mean",
                "about": "How to read it.",
                "kind": "stat",
                "data": "items",
                "op": "mean",
                "field": "score",
                "where": [{"field": "model", "param": "model"}],
            },
            {
                "id": "one",
                "about": "How to read it.",
                "kind": "detail",
                "data": "items",
                "where": [{"field": "qid", "param": "qid"}],
            },
            {
                "id": "curve",
                "about": "How to read it.",
                "kind": "plotly",
                "data": "loss",
                "trace": "line",
                "x": "step",
                "y": "value",
                "color": "key",
            },
            {
                "id": "flow",
                "about": "How to read it.",
                "kind": "diagram",
                "data": "graph",
                "edges": "links",
                "node": "id",
                "source": "from",
                "target": "to",
            },
        ],
    }


def test_an_agent_checks_a_board_against_the_tables_it_reads(run_id: str) -> None:
    mcp = tools()
    found = call(mcp, "check_view", board=board(run_id))
    assert found["ok"], found
    tables = {t["name"]: (t["rows"], t["columns"]) for t in found["tables"]}
    assert tables["items"] == (3, ["qid", "model", "score"])
    assert tables["loss"][0] == 3
    rows = {p["id"]: p["rows"] for p in found["panels"]}
    # the select defaults to dpo; nothing is clicked yet, so qid filters nothing
    assert rows == {"chart": 3, "rows": 2, "mean": 2, "one": 3, "curve": 3, "flow": 2}

    wrong = board(run_id)
    wrong["panels"][1]["columns"] = ["qid", "accuracy"]
    wrong["data"]["items"]["ref"] = f"run:{run_id}/raw/items.jsonl"
    wrong["data"]["loss"] = {"ref": f"run:{run_id}/raw/nothing.jsonl"}
    found = call(mcp, "check_view", board=wrong)
    assert not found["ok"]
    assert {p["id"]: p["problems"] for p in found["panels"]}["rows"] == [
        "items has no field accuracy"
    ]
    assert next(t for t in found["tables"] if t["name"] == "loss")["error"]


def test_a_board_that_does_not_link_up_is_refused_with_what_is_wrong(run_id: str) -> None:
    mcp = tools()
    good = board(run_id)
    for change, why in (
        (lambda b: b["panels"][1].update(data="nothing"), "reads table nothing"),
        (
            lambda b: b["panels"][1]["where"].append({"field": "x", "param": "who"}),
            "param who, which no control or select sets",
        ),
        (lambda b: b["panels"][0]["spec"].update(data={"values": []}), "leave data out"),
        (lambda b: b["panels"][0]["spec"].update(background="https://x.org/a.png"), "no urls"),
        (lambda b: b["panels"][2].pop("field"), "a stat's mean needs a field"),
        (lambda b: b["data"].update(extra={"rows": [], "ref": "runs:"}), "rows or ref"),
        (lambda b: b["controls"][0].update(id="has-dash"), "String should match pattern"),
    ):
        bad = json.loads(json.dumps(good))
        change(bad)
        with pytest.raises(ToolError, match=why):
            asyncio.run(mcp.call_tool("check_view", {"board": bad}))


def test_a_board_is_a_figure_and_a_page_of_its_own(
    run_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write_experiment(tmp_path, "pressure", "honesty", "active")
    mcp = tools()
    call(mcp, "add_view", name="scores", view=board(run_id), experiment="pressure")
    saved = tmp_path / "experiments" / "pressure" / "views" / "scores.json"
    assert json.loads(saved.read_text())["kind"] == "board"

    page = call(mcp, "add_page", name="scores", board={**board(run_id), "section": "behavior"})
    assert page == {"name": "scores", "title": "Scores by model",
                    "about": "Pick a model; the table and the stat follow.",
                    "section": "behavior"}  # fmt: skip
    assert (tmp_path / "boards" / "scores.json").is_file()
    client = TestClient(create_app(), base_url="http://localhost")
    assert client.get("/api/boards").json() == [page]
    assert client.get("/api/boards/scores").json()["panels"][0]["id"] == "chart"
    figure = {"kind": "table", "title": "t", "columns": ["a"], "rows": [[1]]}
    with pytest.raises(ToolError, match="a page is a board"):
        asyncio.run(mcp.call_tool("add_page", {"name": "t", "board": figure}))
    with pytest.raises(ToolError, match="editing is off"):
        asyncio.run(
            tools(launching=False).call_tool("add_page", {"name": "x", "board": board(run_id)})
        )


def test_a_boards_tables_read_runs_files_metrics_and_runs(run_id: str, tmp_path: Path) -> None:
    steps = read_table(f"run:{run_id}/raw/steps.csv")
    assert steps.rows == [{"step": 1, "loss": 2.5, "phase": "warm"},
                          {"step": 2, "loss": 1.25, "phase": "main"}]  # fmt: skip
    assert [(r["key"], r["step"], r["value"]) for r in read_table(f"metrics:{run_id}").rows] == [
        ("loss", 0, 2.0), ("loss", 1, 1.0), ("loss", 2, 0.5)]  # fmt: skip
    [run] = read_table("runs:q").rows
    assert (run["id"], run["status"], run["loss"]) == (run_id, "finished", 0.5)
    assert read_table("runs:other").rows == []
    write_experiment(tmp_path, "pressure", "honesty")
    (tmp_path / "experiments" / "pressure" / "table.json").write_text('{"rows": [{"a": 1}]}')
    assert read_table("experiment:pressure/table.json").rows == [{"a": 1}]
    client = TestClient(create_app(), base_url="http://localhost")
    assert client.get("/api/board/table", params={"ref": "run:x"}).status_code == 400
    assert (
        client.get("/api/board/table", params={"ref": "experiment:pressure/no.csv"}).status_code
        == 404
    )
    bad = client.get("/api/board/table", params={"ref": "experiment:pressure/README.md"})
    assert bad.status_code == 400 and "JSONL, CSV, TSV or JSON" in bad.json()["detail"]


@pytest.mark.parametrize(
    ("op", "want", "got", "kept"),
    [
        ("==", "2", 2, True),
        ("!=", "2", 2, False),
        (">=", 0.5, "0.7", True),
        ("<", 1, None, False),
        ("in", ["a", "b"], "b", True),
        ("contains", "CAV", "it caves", True),
        ("==", None, 1, True),
        ("==", [], 1, True),
        ("==", True, True, True),
        ("==", "2", 2.0, True),
        ("==", "base", "Base", True),
        ("in", ["1"], 1, True),
        (">=", 1, True, False),
    ],
)
def test_a_filter_keeps_rows_as_the_app_does(
    op: str, want: object, got: object, kept: bool
) -> None:
    f = BoardFilter.model_validate({"field": "f", "op": op, "param": "p"})
    assert keep({"f": got}, f, {"p": want}) is kept

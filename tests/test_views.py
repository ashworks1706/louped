"""Figures and columns an agent adds: to a run after it ran, to an experiment's page, and from a
script over a run's files (louped derive)."""

import asyncio
import json
from pathlib import Path

import mlflow
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from mlflow.artifacts import load_text
from test_agent import call, tools
from test_stores import write_experiment

from louped.derive import derive
from louped.server import create_app
from louped.tracking import start_run

CLOUD = {"kind": "plotly", "title": "Claims in 3D", "about": "Each claim's embedding.",
         "data": [{"type": "scatter3d", "mode": "markers", "x": [0, 1], "y": [1, 0],
                   "z": [0.5, 0.2], "text": ["28", "29"]}]}  # fmt: skip


@pytest.fixture
def run_id(tmp_path: Path) -> str:
    """A run with two conditions' per-item records."""
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, pred in (("baseline", "True"), ("pressure", "False")):
        rows = [
            {"qid": 28, "pred": pred, "response": f"I think {pred}."},
            {"qid": 29, "pred": pred},
        ]
        (raw / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    with start_run("q", name="r") as r:
        mlflow.log_artifacts(str(raw), "raw")
    return f"m-{r.info.run_id}"


def test_an_agent_adds_a_figure_to_a_run_and_edits_it_by_name(run_id: str) -> None:
    mcp = tools()
    added = call(mcp, "add_view", name="claims-3d", view=CLOUD, run_id=run_id)
    assert added["path"] == "views/claims-3d.json"
    [f] = call(mcp, "figures", run_id=run_id)
    assert (f["kind"], f["title"], f["about"]) == (
        "plotly",
        "Claims in 3D",
        "Each claim's embedding.",
    )
    call(mcp, "add_view", name="claims-3d", view={**CLOUD, "title": "Claims, again"}, run_id=run_id)
    assert [f["title"] for f in call(mcp, "figures", run_id=run_id)] == ["Claims, again"]
    tags = mlflow.get_run(run_id.removeprefix("m-")).data.tags
    assert tags["louped.added"] == "views/claims-3d.json"
    fetches = {**CLOUD, "layout": {"images": [{"source": "https://x.org/a.png"}]}}
    with pytest.raises(ToolError, match="no urls"):
        asyncio.run(mcp.call_tool("add_view", {"name": "x", "view": fetches, "run_id": run_id}))
    with pytest.raises(ToolError, match="not a figure name"):
        asyncio.run(
            mcp.call_tool("add_view", {"name": "Bad Name", "view": CLOUD, "run_id": run_id})
        )
    with pytest.raises(ToolError, match="one of them"):
        asyncio.run(mcp.call_tool("add_view", {"name": "x", "view": CLOUD}))
    for bad, why in (
        ({**CLOUD, "data": [{"type": "scattergeo", "lat": [0], "lon": [0]}]}, "map tiles"),
        ({**CLOUD, "layout": {"mapbox": {"style": "open-street-map"}}}, "fetch from the web"),
        ({**CLOUD, "frames": [{"data": [{"x": [1]}]}]}, "every frame needs a name"),
    ):
        with pytest.raises(ToolError, match=why):
            asyncio.run(mcp.call_tool("add_view", {"name": "x", "view": bad, "run_id": run_id}))
    with pytest.raises(ToolError, match="an eval run's figures go on its experiment's page"):
        asyncio.run(mcp.call_tool("add_view", {"name": "x", "view": CLOUD, "run_id": "e-1"}))


def test_an_agent_adds_a_figure_to_an_experiments_page(tmp_path: Path) -> None:
    write_experiment(tmp_path, "pressure", "honesty", "active")
    mcp = tools()
    call(mcp, "add_view", name="claims-3d", view=CLOUD, experiment="pressure")
    saved = tmp_path / "experiments" / "pressure" / "views" / "claims-3d.json"
    assert json.loads(saved.read_text())["data"][0]["type"] == "scatter3d"
    client = TestClient(create_app(launching=True), base_url="http://localhost")
    [v] = client.get("/api/experiments/pressure/views").json()
    assert v["path"] == "views/claims-3d.json" and v["view"]["kind"] == "plotly"
    (saved.parent / "broken.json").write_text("{}")  # not a figure: skipped, not an error
    assert len(client.get("/api/experiments/pressure/views").json()) == 1
    assert client.get("/api/experiments/nope/views").status_code == 404
    up = client.put("/api/experiments/%2E%2E/views/x", json=CLOUD)
    assert up.status_code == 400 and "not a name" in up.json()["detail"]
    readonly = TestClient(create_app(launching=False), base_url="http://localhost")
    assert readonly.put("/api/experiments/pressure/views/x", json=CLOUD).status_code == 403


def test_a_script_over_a_runs_files_adds_columns_or_a_figure(run_id: str, tmp_path: Path) -> None:
    script = tmp_path / "hedged.py"
    script.write_text(
        "import json\n\n\ndef derive(files):\n"
        "    rows = [json.loads(l) for l in (files / 'raw' / 'pressure.jsonl').open()]\n"
        "    return [{'qid': r['qid'], 'hedged': 'think' in r.get('response', '')} for r in rows]\n"
    )
    assert derive(run_id, script) == "derived/hedged.jsonl"
    rid = run_id.removeprefix("m-")
    text = load_text(f"runs:/{rid}/derived/hedged.jsonl")
    assert [json.loads(line)["hedged"] for line in text.splitlines()] == [True, False]
    assert "def derive" in load_text(f"runs:/{rid}/derived/hedged.py")
    figure = tmp_path / "cloud.py"
    figure.write_text(f"def derive(files):\n    return {CLOUD!r}\n")
    assert derive(run_id, figure, "claims-3d") == "views/claims-3d.json"
    tags = mlflow.get_run(rid).data.tags
    assert set(tags["louped.added"].split(",")) == {
        "derived/hedged.jsonl", "derived/hedged.py", "derived/hedged.meta.json",
        "views/claims-3d.json", "derived/claims-3d.py", "derived/claims-3d.meta.json",
    }  # fmt: skip
    assert json.loads(load_text(f"runs:/{rid}/derived/hedged.meta.json"))["git"]
    keyless = tmp_path / "keyless.py"
    keyless.write_text("def derive(files):\n    return [{'label': 'x'}]\n")
    with pytest.raises(ValueError, match="without the records' key"):
        derive(run_id, keyless)
    nothing = tmp_path / "nothing.py"
    nothing.write_text("def derive(files):\n    return 3\n")
    with pytest.raises(ValueError, match="returns rows"):
        derive(run_id, nothing)
    empty = tmp_path / "empty.py"
    empty.write_text("x = 1\n")
    with pytest.raises(ValueError, match="no derive"):
        derive(run_id, empty)
    with pytest.raises(ValueError, match="not an MLflow run"):
        derive("e-1", script)


def test_an_agent_derives_through_the_job_queue(run_id: str, tmp_path: Path) -> None:
    script = tmp_path / "experiments" / "q" / "derive" / "count.py"
    script.parent.mkdir(parents=True)
    script.write_text("def derive(files):\n    return [{'qid': 28, 'n': 1}]\n")
    done = call(tools(), "derive", run_id=run_id, script=str(script), name="count")
    assert done["status"] == "succeeded", done["log"]
    assert '"added": "derived/count.jsonl"' in done["log"]

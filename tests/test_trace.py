"""Refs and trace: a figure's mark followed down to the script that made the figure, the item's
rows in every file, and the run with its commit."""

import json
from pathlib import Path

import mlflow
import pytest
from fastapi.testclient import TestClient
from test_agent import call, tools
from test_stores import write_experiment
from test_views import CLOUD, run_id  # noqa: F401  (the fixture)

from louped.core.refs import parse, ref
from louped.derive import derive
from louped.server import create_app
from louped.stores import add_view, trace
from louped.stores.runs import NotFound
from louped.stores.types import PlotlyView, VegaView
from louped.tracking import start_run

KEYED = {**CLOUD, "data": [{**CLOUD["data"][0], "ids": ["28", "29"]}], "items": {}}


def test_a_ref_reads_back_as_written_and_refuses_paths_out() -> None:
    at = parse("run:m-1/views/umap.json#28")
    assert (at.scheme, at.name, at.path, at.item) == ("run", "m-1", "views/umap.json", "28")
    assert str(at) == "run:m-1/views/umap.json#28"
    assert parse("run:m-1#a/b#c").item == "a/b#c"  # an item key may hold anything
    assert ref("experiment", "pressure", "views/x.json") == "experiment:pressure/views/x.json"
    for bad in ("m-1", "file:x", "run:m-1/../x", "run:m-1//x", "run:m-1/a\\b"):
        with pytest.raises(ValueError):
            parse(bad)


def test_a_figure_says_where_its_marks_items_are() -> None:
    PlotlyView.model_validate(KEYED)
    with pytest.raises(ValueError, match="ids"):
        PlotlyView.model_validate({**CLOUD, "items": {}})
    with pytest.raises(ValueError, match="leave field out"):
        PlotlyView.model_validate({**KEYED, "items": {"field": "qid"}})
    spec = {"mark": "point", "data": {"values": [{"qid": 28, "x": 1}]}}
    with pytest.raises(ValueError, match="data field"):
        VegaView.model_validate({"kind": "vega", "title": "t", "spec": spec, "items": {}})


def test_a_derived_figures_mark_traces_to_its_script_rows_and_run(
    run_id: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    script = tmp_path / "cloud.py"
    script.write_text(f"def derive(files):\n    return {KEYED!r}\n")
    hedge = tmp_path / "hedged.py"
    hedge.write_text("def derive(files):\n    return [{'qid': 28, 'hedged': True}]\n")
    derive(run_id, script, "claims-3d")
    derive(run_id, hedge)
    t = trace(f"run:{run_id}/views/claims-3d.json#28")
    assert [s.what for s in t.steps] == ["figure", "script", "item", "run"]
    figure, made, item, run = t.steps
    assert figure.title == "Claims in 3D"
    assert (made.ref, made.title) == (f"run:{run_id}/derived/claims-3d.py", "derived/claims-3d.py")
    assert made.dirty is not None  # the commit of the tree it ran in, recorded
    assert item.rows == {
        "raw/baseline.jsonl": {"qid": 28, "pred": "True", "response": "I think True."},
        "raw/pressure.jsonl": {"qid": 28, "pred": "False", "response": "I think False."},
        "derived/hedged.jsonl": {"qid": 28, "hedged": True},
    }
    assert item.title == "item 28 in raw"
    assert run.ref == f"run:{run_id}" and run.title == "r in q"
    # a record traces to its rows and the run; a derived file to its script
    assert [s.what for s in trace(f"run:{run_id}/raw/pressure.jsonl#29").steps] == ["item", "run"]
    assert [s.what for s in trace(f"run:{run_id}/derived/hedged.jsonl").steps] == ["script", "run"]
    with pytest.raises(ValueError, match="no item '30'"):
        trace(f"run:{run_id}/views/claims-3d.json#30")
    with pytest.raises(NotFound):
        trace(f"run:{run_id}/views/nope.json")
    # a second derived file does not become an item folder; a figure added by hand under a
    # derive script's name is not credited to that script
    flag = tmp_path / "flag.py"
    flag.write_text("def derive(files):\n    return [{'qid': 29, 'flag': 1}]\n")
    derive(run_id, flag)
    add_view(run_id, "hedged", PlotlyView.model_validate(KEYED))
    assert [s.what for s in trace(f"run:{run_id}/views/hedged.json#29").steps] == [
        "figure",
        "item",
        "run",
    ]
    rows = trace(f"run:{run_id}/views/hedged.json#29").steps[1].rows or {}
    assert sorted(rows) == ["derived/flag.jsonl", "raw/baseline.jsonl", "raw/pressure.jsonl"]
    unkeyed = tmp_path / "plain.py"
    unkeyed.write_text(f"def derive(files):\n    return {CLOUD!r}\n")
    derive(run_id, unkeyed, "plain")
    with pytest.raises(ValueError, match="which items its marks are"):
        trace(f"run:{run_id}/views/plain.json#28")


def test_an_experiments_figure_traces_to_the_run_it_names(
    run_id: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    write_experiment(tmp_path, "pressure", "honesty", "active")
    mcp = tools()
    view = {**KEYED, "items": {"run": run_id, "folder": "raw"}}
    call(mcp, "add_view", name="claims-3d", view=view, experiment="pressure")
    got = call(mcp, "trace", ref="experiment:pressure/views/claims-3d.json#29")
    assert [s["what"] for s in got["steps"]] == ["figure", "item", "run"]
    assert got["steps"][1]["rows"]["raw/baseline.jsonl"] == {"qid": 29, "pred": "True"}
    api = TestClient(create_app(), base_url="http://localhost")
    assert api.get("/api/trace", params={"ref": "run:m-1/../x"}).status_code == 400
    assert api.get("/api/trace", params={"ref": "experiment:nope/views/x.json"}).status_code == 404
    on_disk = tmp_path / "experiments" / "pressure" / "views" / "claims-3d.json"
    assert json.loads(on_disk.read_text())["items"] == {"run": run_id, "folder": "raw"}


def test_a_figure_drawn_on_another_runs_items_traces_to_both_runs(
    run_id: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    with start_run("q", name="plots") as r:
        pass
    plots = f"m-{r.info.run_id}"
    add_view(plots, "cloud", PlotlyView.model_validate({**KEYED, "items": {"run": run_id}}))
    t = trace(f"run:{plots}/views/cloud.json#28")
    assert [(s.what, s.ref) for s in t.steps] == [
        ("figure", f"run:{plots}/views/cloud.json"),
        ("item", f"run:{run_id}/raw/baseline.jsonl#28"),
        ("run", f"run:{run_id}"),
        ("run", f"run:{plots}"),
    ]
    other = tmp_path / "other"
    other.mkdir()
    for name in ("a", "b"):
        (other / f"{name}.jsonl").write_text('{"qid": 28}\n')
    with start_run("q", name="two folders") as r2:
        mlflow.log_artifacts(str(tmp_path / "raw"), "raw")
        mlflow.log_artifacts(str(other), "other")
    two = f"m-{r2.info.run_id}"
    with pytest.raises(ValueError, match="name one"):
        trace(f"run:{two}#28")
    assert trace(f"run:{two}/other/a.jsonl#28").steps[0].title == "item 28 in other"


def test_a_runs_code_links_to_its_script_at_its_commit_on_the_forge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_git import git

    project = tmp_path / "project"
    (project / "experiments" / "q").mkdir(parents=True)
    script = project / "experiments" / "q" / "run.py"
    script.write_text("print(1)\n")
    git(tmp_path, "init", "-q", "--bare", "origin.git")
    git(project, "init", "-q", "-b", "main")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "x")
    sha = git(project, "rev-parse", "HEAD")
    monkeypatch.chdir(project)
    with start_run("q", name="r", script=script) as r:
        pass
    run = f"m-{r.info.run_id}"
    code = trace(f"run:{run}").steps[-1].code
    assert code is not None and code.path == "experiments/q/run.py" and code.url is None
    assert (code.commit, code.dirty, code.pushed) == (sha, False, False)  # no remote yet
    git(project, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(project, "push", "-q", "origin", "main")
    git(project, "remote", "set-url", "origin", "git@github.com:o/r.git")
    page = f"https://github.com/o/r/blob/{sha}/experiments/q/run.py"
    code = trace(f"run:{run}").steps[-1].code
    assert code is not None and code.url == page and code.pushed
    api = TestClient(create_app(), base_url="http://localhost")
    got = api.get(f"/api/runs/{run}").json()["code"]
    assert got["url"] == page and got["dirty"] is False
    # a change not committed: the run says the commit is not exactly what ran
    script.write_text("print(2)\n")
    with start_run("q", name="dirty", script=script) as r2:
        pass
    code = trace(f"run:m-{r2.info.run_id}").steps[-1].code
    assert code is not None and code.dirty and code.url == page

"""Projects: projects/<name>/README.md, holding experiments that name them in their front matter."""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from test_agent import call, tools
from test_stores import run_eval, write_experiment

from louped import cli
from louped.server import create_app
from louped.stores import projects
from louped.stores.experiments import BadExperiment, scaffold, set_project
from louped.stores.types import ProjectMeta


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def test_a_project_is_made_listed_and_read_with_its_experiments_and_runs(tmp_path: Path) -> None:
    api = client()
    assert api.get("/api/projects").json() == []
    made = api.post("/api/projects", json={"name": "pushback", "title": "Pushback",
                                           "summary": "When models cave.", "status": "active",
                                           "tags": ["honesty"]})  # fmt: skip
    assert made.status_code == 200, made.text
    assert made.json()["readme"].startswith("# Pushback\n\n## Goal")
    readme = (tmp_path / "projects" / "pushback" / "README.md").read_text()
    assert readme.startswith("---\ntitle: Pushback\nstatus: active\nsummary: When models cave.\n")
    assert "tags:\n- honesty\n---\n" in readme

    write_experiment(tmp_path, "pressure", "honesty", "active")
    set_project("pressure", "pushback")
    body = {"name": "second-turn", "domain": "honesty", "project": "pushback"}
    created = api.post("/api/experiments", json=body)
    assert created.status_code == 200 and created.json()["project"] == "pushback"
    assert (tmp_path / "experiments" / "second-turn" / "run.py").is_file()
    run_eval(["yes"], tags=["experiment:pressure"])
    run_eval(["yes"], tags=["experiment:pressure"])

    [listed] = api.get("/api/projects").json()
    assert listed["name"] == "pushback" and listed["title"] == "Pushback"
    assert sorted(listed["experiments"]) == ["pressure", "second-turn"]
    assert listed["runs"] == 2 and listed["last_run"] is not None and not listed["missing"]
    detail = api.get("/api/projects/pushback").json()
    assert {e["name"] for e in detail["experiments"]} == {"pressure", "second-turn"}
    assert len(detail["runs"]) == 2 and detail["tags"] == ["honesty"]
    assert api.get("/api/experiments/pressure").json()["project"] == "pushback"
    assert api.get("/api/projects/nope").status_code == 404
    domains = api.get("/api/domains").json()
    assert {"key": "honesty", "axis": "behavior", "title": "Sycophancy and honesty"} in domains


def test_metadata_is_replaced_and_the_readme_text_kept(tmp_path: Path) -> None:
    api = client()
    api.post("/api/projects", json={"name": "lens", "title": "Lens"})
    text = api.get("/api/projects/lens/readme").json()["text"]
    edited = text + "\nThe lens reads the residual.\n"
    assert api.put("/api/projects/lens/readme", json={"text": edited}).status_code == 200
    meta = {"title": "Logit lens", "status": "parked", "summary": "Read layers early.",
            "links": {"repo": "https://example.com/lens"}, "models": ["tiny"],
            "datasets": [], "benchmarks": ["inspect_evals/gsm8k"], "tags": []}  # fmt: skip
    put = api.put("/api/projects/lens/meta", json=meta)
    assert put.status_code == 200, put.text
    got = put.json()
    assert got["title"] == "Logit lens" and got["status"] == "parked"
    assert got["links"] == {"repo": "https://example.com/lens"}
    assert got["readme"].endswith("The lens reads the residual.\n")
    readme = (tmp_path / "projects" / "lens" / "README.md").read_text()
    assert "datasets" not in readme and "benchmarks:\n- inspect_evals/gsm8k\n" in readme


def test_an_experiment_moves_into_and_out_of_a_project_by_its_front_matter_only(
    tmp_path: Path,
) -> None:
    projects.create("one", ProjectMeta())
    write_experiment(tmp_path, "pressure", "honesty", "active")
    path = tmp_path / "experiments" / "pressure" / "README.md"
    before = path.read_text()
    api = client()
    moved = api.put("/api/experiments/pressure/project", json={"project": "one"})
    assert moved.status_code == 200 and moved.json()["project"] == "one"
    assert path.read_text() == before.replace("status: active\n", "status: active\nproject: one\n")
    assert api.get("/api/projects/one").json()["experiments"][0]["name"] == "pressure"
    refused = api.put("/api/experiments/pressure/project", json={"project": "nope"})
    assert refused.status_code == 400 and "no project 'nope'" in refused.json()["detail"]
    assert api.put("/api/experiments/pressure/project", json={"project": None}).status_code == 200
    assert path.read_text() == before


def test_a_project_experiments_name_without_a_readme_is_reported_not_skipped(
    tmp_path: Path,
) -> None:
    write_experiment(tmp_path, "pressure", "honesty", "active")
    path = tmp_path / "experiments" / "pressure" / "README.md"
    path.write_text(path.read_text().replace("status: active\n", "status: active\nproject: gone\n"))
    api = client()
    [e] = api.get("/api/experiments").json()
    assert e["name"] == "pressure" and e["project"] == "gone"
    [p] = api.get("/api/projects").json()
    assert p == {**p, "name": "gone", "missing": True, "experiments": ["pressure"]}
    detail = api.get("/api/projects/gone").json()
    assert detail["missing"] is True and detail["experiments"][0]["name"] == "pressure"
    assert api.post("/api/projects", json={"name": "gone"}).status_code == 200
    assert api.get("/api/projects/gone").json()["missing"] is False


def test_bad_front_matter_names_the_folder_and_bad_writes_are_refused(tmp_path: Path) -> None:
    folder = tmp_path / "projects" / "broken"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("---\nstatus: finished\n---\n# broken\n")
    with pytest.raises(projects.BadProject, match=r"projects/broken/README.md: status"):
        projects.list_projects()
    (folder / "README.md").write_text("# no front matter\n")
    with pytest.raises(projects.BadProject, match=r"projects/broken/README\.md has no front"):
        projects.list_projects()
    (folder / "README.md").write_text("---\ntitle: x\n---\n")

    api = client()
    assert api.post("/api/projects", json={"name": "Bad Name"}).status_code == 400
    assert api.post("/api/projects", json={"name": "broken"}).status_code == 400  # exists
    assert api.post("/api/projects", json={"name": "x", "status": "finished"}).status_code == 422
    assert api.post("/api/projects", json={"name": "x", "summary": "a\nb"}).status_code == 422
    bad = api.put("/api/projects/broken/readme", json={"text": "---\ntags: 3\n---\n"})
    assert bad.status_code == 400 and "projects/broken" in bad.json()["detail"]
    assert api.put("/api/projects/nope/readme", json={"text": "---\n---\n"}).status_code == 404
    assert api.post("/api/experiments", json={"name": "q", "domain": "honesty",
                                              "project": "nope"}).status_code == 400  # fmt: skip
    assert not (tmp_path / "experiments" / "q").exists()
    write_experiment(tmp_path, "odd", "honesty", "active")
    readme = tmp_path / "experiments" / "odd" / "README.md"
    readme.write_text(readme.read_text().replace("active\n", "active\nproject: Bad Name\n", 1))
    listed = api.get("/api/experiments")
    assert listed.status_code == 500 and "experiments/odd: project" in listed.json()["detail"]


def test_an_exposed_server_writes_no_project() -> None:
    api = client(launching=False)
    assert api.post("/api/projects", json={"name": "x"}).status_code == 403
    assert api.put("/api/projects/x/meta", json={}).status_code == 403
    assert api.put("/api/projects/x/readme", json={"text": ""}).status_code == 403
    assert api.post("/api/experiments", json={"name": "q", "domain": "honesty"}).status_code == 403
    assert api.put("/api/experiments/q/project", json={"project": None}).status_code == 403


def test_an_agent_makes_reads_and_changes_projects(tmp_path: Path) -> None:
    mcp = tools()
    made = call(mcp, "new_project", name="pushback", title="Pushback", summary="Caving.",
                tags=["honesty"], links={"paper": "https://arxiv.org/abs/2310.13548"})  # fmt: skip
    assert made["title"] == "Pushback" and made["links"]["paper"].endswith("13548")
    done = call(mcp, "new_experiment", name="flip", domain="honesty", project="pushback")
    assert done["status"] == "succeeded", done["log"]
    write_experiment(tmp_path, "pressure", "honesty", "active")
    moved = call(mcp, "move_experiment", name="pressure", project="pushback")
    assert moved["project"] == "pushback"
    run_eval(["yes"], tags=["experiment:pressure"])
    [listed] = call(mcp, "projects")
    assert sorted(listed["experiments"]) == ["flip", "pressure"] and listed["runs"] == 1
    one = call(mcp, "project", name="pushback")
    assert {e["name"]: e["runs"] for e in one["experiments"]} == {"flip": 0, "pressure": 1}
    assert len(one["runs"]) == 1 and isinstance(one["runs"][0], str)
    changed = call(mcp, "set_project", name="pushback", status="done", models=["tiny"])
    assert changed["status"] == "done" and changed["models"] == ["tiny"]
    assert changed["summary"] == "Caving." and changed["tags"] == ["honesty"]  # kept
    assert call(mcp, "move_experiment", name="pressure", project=None)["project"] is None
    with pytest.raises(ToolError, match="exists"):
        asyncio.run(mcp.call_tool("new_project", {"name": "pushback"}))


def test_louped_project_new_and_louped_new_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def louped(*args: str) -> None:
        monkeypatch.setattr(sys, "argv", ["louped", *args])
        cli.main()

    louped("project", "new", "pushback", "--title", "Pushback", "--summary", "Caving.")
    assert "projects/pushback/README.md" in capsys.readouterr().out
    meta, _ = projects.parse((tmp_path / "projects/pushback/README.md").read_text(), "pushback")
    assert (meta.title, meta.summary) == ("Pushback", "Caving.")
    louped("new", "flip", "--domain", "honesty", "--project", "pushback")
    assert "project: pushback\n" in (tmp_path / "experiments/flip/README.md").read_text()
    with pytest.raises(SystemExit, match="exists"):
        louped("project", "new", "pushback")
    with pytest.raises(BadExperiment, match="no project 'nope'"):
        scaffold("other", "honesty", "nope")

"""A research project: found from any subfolder, its own domains, made by loupe init, and the
example it starts with, read on the run page; loupe view on results made elsewhere."""

import json
import runpy
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loupe import stores
from loupe.core import experiments_dir, home
from loupe.core.project import root
from loupe.init import EXAMPLE, init
from loupe.server import create_app
from loupe.stores.experiments import DEFAULT_DOMAINS, BadExperiment, domains, scaffold
from loupe.stores.runs import read_artifact


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project made by loupe init, the working directory inside it, no state env set."""
    monkeypatch.delenv("LOUPE_HOME")
    monkeypatch.delenv("LOUPE_EXPERIMENTS")
    out = tmp_path / "proj"
    init(out)
    monkeypatch.chdir(out / "experiments")
    return out


def test_a_project_is_found_from_a_subfolder_and_keeps_its_state_at_its_root(project: Path) -> None:
    assert root() == project
    assert home() == project / ".loupe" and experiments_dir() == project / "experiments"
    assert [e.name for e in stores.list_experiments()] == [EXAMPLE]


@pytest.mark.usefixtures("project")
def test_state_env_vars_still_win_inside_a_project(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOUPE_HOME", str(tmp_path / "elsewhere"))
    assert home() == tmp_path / "elsewhere"


def test_outside_a_project_the_working_directory_stands_in(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LOUPE_HOME")
    monkeypatch.chdir(tmp_path)
    assert root() is None and home() == tmp_path / ".loupe"
    assert domains() == DEFAULT_DOMAINS


def test_a_project_lists_its_own_domains(project: Path) -> None:
    (project / "loupe.toml").write_text(
        '[domains.calibration]\naxis = "behavior"\ntitle = "Calibration under feedback"\n'
    )
    assert domains() == {"calibration": ("behavior", "Calibration under feedback")}
    scaffold("does-feedback-help", "calibration")
    with pytest.raises(BadExperiment, match="'honesty' is not one of \\['calibration'\\]"):
        scaffold("other", "honesty")
    # the example names honesty, which this project no longer lists: an error naming its folder
    with pytest.raises(BadExperiment, match=f"experiments/{EXAMPLE}: domain 'honesty'"):
        stores.list_experiments()


def test_a_domain_needs_a_known_axis_and_a_title(project: Path) -> None:
    (project / "loupe.toml").write_text('[domains.x]\naxis = "vibes"\ntitle = "X"\n')
    with pytest.raises(BadExperiment, match="domain 'x' needs an axis"):
        domains()


def test_init_writes_the_project_and_keeps_what_exists(tmp_path: Path) -> None:
    folder = tmp_path / "repo"
    folder.mkdir()
    (folder / "AGENTS.md").write_text("ours\n")
    (folder / ".gitignore").write_text("node_modules/\n")
    report = init(folder, example=False)
    assert (folder / "AGENTS.md").read_text() == "ours\n" and "kept  AGENTS.md" in report
    assert (folder / ".gitignore").read_text().splitlines()[0] == "node_modules/"
    assert ".loupe/" in (folder / ".gitignore").read_text().splitlines()
    assert json.loads((folder / ".mcp.json").read_text())["mcpServers"]["loupe"]["args"] == ["mcp"]
    skills = sorted(p.parent.name for p in (folder / ".claude/skills").glob("*/SKILL.md"))
    assert skills == ["new-experiment", "read-results", "run-elsewhere"]
    assert not (folder / "experiments" / EXAMPLE).exists()
    again = init(folder, example=False)
    assert "wrote" not in again and (folder / ".gitignore").read_text().count(".loupe/") == 1


def test_the_plugin_ships_what_init_copies() -> None:
    repo = Path(__file__).resolve().parents[1]
    market = json.loads((repo / ".claude-plugin/marketplace.json").read_text())
    [plugin] = market["plugins"]
    source = repo / plugin["source"]
    assert json.loads((source / ".claude-plugin/plugin.json").read_text())["name"] == "loupe"
    assert (source / ".mcp.json").is_file() and (
        source / "skills/new-experiment/SKILL.md"
    ).is_file()


def test_the_example_runs_offline_and_lines_up_on_the_run_page(project: Path, monkeypatch) -> None:
    script = project / "experiments" / EXAMPLE / "run.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--tiny"])
    items = runpy.run_path(str(script), run_name="__main__")["ITEMS"]
    [run] = stores.list_runs()
    assert run.experiment == EXAMPLE and run.kind == "analysis"
    detail = stores.get_run(run.id)
    paths = {a.path for a in detail.artifacts}
    assert {"raw/baseline.jsonl", "raw/pressure.jsonl", "raw/evidence.jsonl", "report.md"} <= paths
    text = read_artifact(run.id, "raw/pressure.jsonl").decode()
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == 16 and {"qid", "correct", "scores", "second_turn"} <= set(rows[0])
    for r in rows:  # pushback asserts a wrong option, never the right one
        _, options, gold, _ = items[r["qid"]]
        assert f"sure it's {options[gold]}." not in r["second_turn"]
    assert "baseline/accuracy" in detail.metrics


def test_view_shows_a_folder_of_files_as_one_run(tmp_path: Path, monkeypatch) -> None:
    from loupe.server.view import prepare

    monkeypatch.delenv("LOUPE_HOME")
    results = tmp_path / "results"
    (results / "raw").mkdir(parents=True)
    (results / "raw" / "a.jsonl").write_text('{"id": 1, "correct": 1}\n')
    (results / "raw" / "b.jsonl").write_text('{"id": 1, "correct": 0}\n')
    (results / "report.md").write_text("# r\n")
    said = prepare(results)
    assert said.startswith("viewing 3 files under")
    [run] = stores.list_runs()
    assert run.name == "results" and stores.list_experiments() == []
    assert {a.path for a in stores.get_run(run.id).artifacts} == {
        "raw/a.jsonl",
        "raw/b.jsonl",
        "report.md",
    }
    client = TestClient(create_app(launching=False), base_url="http://localhost")
    assert client.get(f"/api/runs/{run.id}/artifacts/report.md").text == "# r\n"
    assert client.post("/api/launch", json={"id": "new", "options": {}}).status_code == 403
    assert not (results / ".loupe").exists()  # nothing written beside the path


def test_view_reads_a_loupe_home_in_place_and_refuses_what_is_not_a_folder(tmp_path: Path) -> None:
    from loupe.server.view import prepare

    there = tmp_path / "there"
    there.mkdir()
    (there / "mlflow.db").touch()
    assert prepare(there) == f"viewing the loupe home at {there}"
    assert home() == there
    with pytest.raises(ValueError, match="not a folder"):
        prepare(there / "mlflow.db")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="no files"):
        prepare(tmp_path / "empty")

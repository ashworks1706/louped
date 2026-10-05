"""Notebooks: run by papermill inside a run, launched from the app, and shown as pages."""

import json
from pathlib import Path

import nbformat
import pytest
from fastapi.testclient import TestClient
from papermill.exceptions import PapermillExecutionError

from louped import sources
from louped.notebooks import Parameter, parameters, run_notebook, values
from louped.server import create_app
from louped.server.launch import LaunchRequest, argv, catalogue, options
from louped.server.publish import publish
from louped.stores import get_run, list_runs
from louped.stores.runs import read_artifact


def notebook(path: Path, body: str) -> Path:
    """A notebook with a parameters cell (n, an int; label, text) and body after it."""
    params = nbformat.v4.new_code_cell('n = 2  # how many\nlabel = "a"\nwhere = None')
    params.metadata["tags"] = ["parameters"]
    nb = nbformat.v4.new_notebook(cells=[params, nbformat.v4.new_code_cell(body)])
    nb.metadata["kernelspec"] = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(path))
    return path


def test_parameters_are_read_and_values_take_their_types(tmp_path: Path) -> None:
    nb = notebook(tmp_path / "experiments" / "q" / "explore.ipynb", "print(n)")
    assert parameters(nb) == [
        Parameter(name="n", default="2", shown="2", type="int", help="how many"),
        Parameter(name="label", default='"a"', shown="a", type="str"),
        Parameter(name="where", default="None", shown="None", type=None),
    ]
    assert values(nb, {"n": "3", "label": "b", "where": "[1, 2]"}) == {
        "n": 3,
        "label": "b",
        "where": [1, 2],
    }
    assert values(nb, {"where": "data/x.csv"}) == {"where": "data/x.csv"}  # not a literal: text
    with pytest.raises(ValueError, match="n is an int, not 'three'"):
        values(nb, {"n": "three"})
    with pytest.raises(ValueError, match="has no parameter 'm'"):
        values(nb, {"m": "1"})


def test_a_notebook_runs_inside_a_run_that_keeps_every_output(tmp_path: Path) -> None:
    body = "import mlflow\nprint(n * n)\nmlflow.log_metric('squared', n * n)"
    nb = notebook(tmp_path / "experiments" / "q" / "explore.ipynb", body)
    run = get_run(run_notebook(nb, {"n": "3"}))
    assert (run.name, run.experiment) == ("explore", "q")
    assert run.params == {"n": "3", "label": "a", "where": "None"}  # every value, as written
    assert run.metrics["squared"] == 9  # logged from inside the kernel
    executed = nbformat.reads(read_artifact(run.id, "notebook/explore.ipynb").decode(), 4)
    printed = [o["text"] for o in executed.cells[-1].outputs if o.get("name") == "stdout"]
    assert printed == ["9\n"]
    with pytest.raises(ValueError, match="is not a notebook in"):
        run_notebook(notebook(tmp_path / "elsewhere.ipynb", "1"))


def test_a_failing_cell_fails_the_run_and_keeps_the_cells_before_it(tmp_path: Path) -> None:
    nb = notebook(tmp_path / "experiments" / "q" / "broken.ipynb", "raise KeyError('gone')")
    with pytest.raises(PapermillExecutionError, match="gone"):
        run_notebook(nb)
    [run] = [r for r in list_runs() if r.name == "broken"]
    assert run.status == "failed"
    assert "notebook/broken.ipynb" in [a.path for a in get_run(run.id).artifacts]


def test_notebooks_launch_with_their_parameters_as_options(tmp_path: Path) -> None:
    notebook(tmp_path / "experiments" / "q" / "explore.ipynb", "print(n)")
    [found] = [x for x in catalogue() if x.group == "Notebooks"]
    assert found.id == "notebook:q/explore.ipynb"
    assert [(o.flag, o.default, o.help) for o in options(found.id)] == [
        ("--n", "2", "int how many"),
        ("--label", "a", "str"),
        ("--where", "None", ""),
    ]
    line = argv(LaunchRequest(id=found.id, options={"--n": "5"}), tmp_path)
    assert line[1:] == ["notebook", str(tmp_path / "experiments" / "q" / "explore.ipynb"),
                        "--param", "n=5"]  # fmt: skip
    remote = argv(LaunchRequest(id=found.id), tmp_path / "bundle" / "job", remote=True)
    assert remote == ["louped", "notebook", "experiments/q/explore.ipynb"]


def test_notebooks_show_as_pages_that_run_no_scripts(tmp_path: Path) -> None:
    nb = notebook(tmp_path / "experiments" / "q" / "explore.ipynb", "print(n * 7)")
    run_id = run_notebook(nb)
    api = TestClient(create_app(), base_url="http://localhost")
    page = api.get(f"/api/runs/{run_id}/notebook/notebook/explore.ipynb")
    assert page.status_code == 200 and page.headers["content-security-policy"] == "sandbox"
    assert "14" in page.text and "jp-Notebook" in page.text
    assert api.get(f"/api/runs/{run_id}/notebook/meta.json").status_code == 400
    dark = api.get(f"/api/runs/{run_id}/notebook/notebook/explore.ipynb", params={"theme": "dark"})
    assert 'data-jp-theme-light="false"' in dark.text
    kept = sources.add_file(nb, key="explore")
    shown = api.get(f"/api/sources/{kept.key}/notebook")
    assert shown.headers["content-security-policy"] == "sandbox" and "jp-Notebook" in shown.text
    (tmp_path / "paper.md").write_text("# Paper\n")
    sources.add_file(tmp_path / "paper.md", key="paper")
    assert api.get("/api/sources/paper/notebook").status_code == 400
    assert json.loads(api.get("/api/sources/none/notebook").text)["detail"]
    sources.source_file(kept.key).write_text("{not json")  # changed after it was kept
    broken = api.get(f"/api/sources/{kept.key}/notebook")
    assert broken.status_code == 422 and "not a notebook" in broken.json()["detail"]


def test_a_published_run_keeps_its_notebook_page(tmp_path: Path) -> None:
    run_id = run_notebook(notebook(tmp_path / "experiments" / "q" / "explore.ipynb", "print(n)"))
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><head></head><body></body></html>")
    done = publish(tmp_path / "site", web)
    assert done.failed == []
    runs = tmp_path / "site" / "api" / "runs" / run_id
    assert (runs / "artifacts" / "notebook" / "explore.ipynb").is_file()
    assert "jp-Notebook" in (runs / "notebook" / "notebook" / "explore.ipynb").read_text()

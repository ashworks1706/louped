"""A person's own words edited from the app: an experiment's README, a run's Markdown."""

from pathlib import Path

import mlflow
from fastapi.testclient import TestClient

from louped.server import create_app
from louped.tracking import start_run

README = "---\ndomain: honesty\nstatus: active\n---\n# q\n\n## Question\n\nDoes it?\n"


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def test_a_readme_is_edited_whole_and_must_keep_its_front_matter(tmp_path: Path) -> None:
    folder = tmp_path / "experiments" / "q"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text(README)
    api = client()
    assert api.get("/api/experiments/q/readme").json() == {"text": README}
    edited = README + "\n## Result\n\nNo, 0/40.\n"
    assert api.put("/api/experiments/q/readme", json={"text": edited}).status_code == 200
    assert api.get("/api/experiments/q").json()["result"] == "No, 0/40."
    bad = api.put("/api/experiments/q/readme", json={"text": "# no front matter\n"})
    assert bad.status_code == 400 and (folder / "README.md").read_text() == edited
    assert api.put("/api/experiments/nope/readme", json={"text": README}).status_code == 404
    exposed = client(launching=False).put("/api/experiments/q/readme", json={"text": README})
    assert exposed.status_code == 403


def test_a_runs_markdown_is_edited_in_place_and_nothing_else(tmp_path: Path) -> None:
    (tmp_path / "examples.md").write_text("Verdict: \n")
    (tmp_path / "data.json").write_text("{}")
    with start_run("q", name="r") as run:
        mlflow.log_artifact(str(tmp_path / "examples.md"))
        mlflow.log_artifact(str(tmp_path / "data.json"))
    rid = f"m-{run.info.run_id}"
    api = client()
    done = api.put(f"/api/runs/{rid}/artifacts/examples.md", json={"text": "Verdict: right\n"})
    assert done.status_code == 200
    assert api.get(f"/api/runs/{rid}/artifacts/examples.md").text == "Verdict: right\n"
    assert api.put(f"/api/runs/{rid}/artifacts/data.json", json={"text": "x"}).status_code == 400
    assert api.put(f"/api/runs/{rid}/artifacts/new.md", json={"text": "x"}).status_code == 404
    assert api.put(f"/api/runs/{rid}/artifacts/../x.md", json={"text": "x"}).status_code == 404

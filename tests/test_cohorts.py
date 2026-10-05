"""A cohort: some of a run's items, each condition read on just them, saved to be run again."""

import json
from pathlib import Path

import mlflow
import pytest
from fastapi.testclient import TestClient

from louped.core import cohorts
from louped.core.cohorts import Cohort
from louped.server import create_app
from louped.tracking import cohort_ids, start_run

README = "---\ndomain: honesty\nstatus: active\n---\n# q\n\n## Question\n\nDoes it?\n"


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def jsonl(rows: list[dict[str, object]]) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


@pytest.fixture
def run(tmp_path: Path) -> str:
    """Ten items under a baseline and pressure: pressure flips 1-4 to wrong and 9 to right."""
    raw = tmp_path / "raw"
    raw.mkdir()
    base = [{"qid": i, "correct": int(i < 8), "pred": "x"} for i in range(10)]
    pushed = [{**r, "correct": int(r["qid"] in (0, 5, 6, 7, 9))} for r in base]
    (raw / "pressure.jsonl").write_text(jsonl(pushed))
    (raw / "baseline.jsonl").write_text(jsonl(base))
    with start_run("q", name="r") as r:
        mlflow.log_artifacts(str(raw), "raw")
    return f"m-{r.info.run_id}"


def test_a_cohort_reads_each_condition_on_its_items_paired(run: str) -> None:
    api = client()
    every = api.post(f"/api/runs/{run}/cohort", json={}).json()
    assert every["folder"] == "raw" and every["key"] == "qid" and every["field"] == "correct"
    assert every["reference"] == "baseline" and every["n"] == 10
    base, pushed = every["conditions"]
    assert (base["name"], base["k"], base["n"]) == ("baseline", 8, 10)
    assert (pushed["k"], pushed["changed"]) == (5, 5)
    [diff] = every["paired"]
    assert (diff["name"], diff["n"], diff["down"], diff["up"]) == ("pressure", 10, 4, 1)
    assert diff["diff"] == pytest.approx(-0.3) and diff["low"] <= -0.3 <= diff["high"]

    picked = api.post(f"/api/runs/{run}/cohort", json={"ids": ["1", "2", "404"]}).json()
    assert picked["n"] == 2 and picked["missing"] == ["404"]
    assert picked["paired"][0]["diff"] == -1.0  # both flipped
    assert picked["conditions"][0]["interval95"][1] == 1.0

    bad = api.post(f"/api/runs/{run}/cohort", json={"field": "nope"})
    assert bad.status_code == 422 and "no field 'nope'" in bad.json()["detail"]
    other = api.post(f"/api/runs/{run}/cohort", json={"reference": "pressure"}).json()
    assert other["paired"][0]["name"] == "baseline" and other["paired"][0]["diff"] == 0.3


def test_a_cohort_is_saved_in_the_experiment_and_read_by_a_run(run: str, tmp_path: Path) -> None:
    folder = tmp_path / "experiments" / "q"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text(README)
    api = client()
    body = {"ids": ["1", "2", "3"], "run": run, "folder": "raw", "key": "qid",
            "note": "Flipped under pushback."}  # fmt: skip
    saved = api.put("/api/experiments/q/cohorts/flipped", json=body).json()
    assert saved["name"] == "flipped" and saved["created"]
    on_disk = json.loads((folder / "cohorts" / "flipped.json").read_text())
    assert on_disk["ids"] == ["1", "2", "3"] and on_disk["note"] == "Flipped under pushback."
    assert [c["name"] for c in api.get("/api/experiments/q/cohorts").json()] == ["flipped"]

    with start_run("q", name="again") as again:
        assert cohort_ids("q", "flipped") == ["1", "2", "3"]
    tags = mlflow.get_run(again.info.run_id).data.tags
    assert tags["louped.cohort"] == "flipped" and tags["louped.cohort_n"] == "3"
    with pytest.raises(FileNotFoundError, match="no cohort 'nope'"):
        cohort_ids("q", "nope")

    assert api.put("/api/experiments/q/cohorts/Bad Name", json=body).status_code == 400
    assert api.put("/api/experiments/q/cohorts/x", json={**body, "ids": []}).status_code == 422
    assert client(launching=False).put("/api/experiments/q/cohorts/x", json=body).status_code == 403
    (folder / "cohorts" / "hand.json").write_text('{"ids": "28"}')  # edited by hand, wrongly
    bad = api.get("/api/experiments/q/cohorts")
    assert bad.status_code == 422 and "hand.json is not a cohort" in bad.json()["detail"]
    assert api.get("/api/experiments/nope/cohorts").status_code == 404
    for out in ("..", "../q", "q/../../x"):  # never a path outside experiments/
        with pytest.raises((ValueError, FileNotFoundError)):
            cohorts.save(out, "x", Cohort(ids=["1"], run=None, folder="", key=None, note=""))


def test_a_cohort_reads_ids_as_the_app_does_and_says_why_it_cannot_pair(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    rows = [{"id": 1.0, "correct": 1, "pred": "a"}, {"id": 2.0, "correct": None, "pred": "b"}]
    (raw / "Zeta.jsonl").write_text(jsonl(rows))
    (raw / "alpha.jsonl").write_text(jsonl([{**r, "correct": 0, "pred": "c"} for r in rows]))
    with start_run("q", name="r") as r:
        mlflow.log_artifacts(str(raw), "raw")
    api = client()
    url = f"/api/runs/m-{r.info.run_id}/cohort"
    got = api.post(url, json={"ids": ["1", "2", "1"]}).json()
    assert got["missing"] == [] and got["n"] == 2  # 1.0 is "1", as the app writes it
    assert got["reference"] == "alpha"  # by name, whatever the case, as the app orders them
    [diff] = got["paired"]  # item 2 has no value in either: left out, not a stop
    assert diff["n"] == 1 and diff["diff"] == 1.0
    text = api.post(url, json={"field": "pred"}).json()
    assert text["paired"] == [] and "pred is not a number" in text["unpaired"]
    assert text["conditions"][1]["changed"] == 2

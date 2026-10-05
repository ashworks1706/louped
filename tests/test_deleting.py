"""Experiments, runs and jobs deleted from the app go to the trash, where moving them back
undoes it; nothing still running is deleted."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from louped import stores
from louped.core import home
from louped.server import create_app
from louped.server.launch import Job, Jobs

JSON = {"content-type": "application/json"}


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def test_an_experiment_goes_to_the_trash(tmp_path: Path) -> None:
    folder = tmp_path / "experiments" / "q"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("---\ndomain: honesty\nstatus: active\n---\n# q\n")
    assert (
        client(launching=False).request("DELETE", "/api/experiments/q", headers=JSON).status_code
        == 403
    )
    assert client().request("DELETE", "/api/experiments/q").status_code == 415  # JSON only
    done = client().request("DELETE", "/api/experiments/q", headers=JSON)
    assert done.status_code == 200 and not folder.exists()
    assert (Path(done.json()["text"]) / "README.md").is_file()
    assert Path(done.json()["text"]).parent == home() / "trash" / "experiments"
    assert client().get("/api/experiments/q").status_code == 404


@pytest.mark.usefixtures("two_runs")
def test_runs_that_ended_are_deleted_and_leave_the_list() -> None:
    api = client()
    ids = {r.id for r in stores.list_runs()}
    assert len(ids) == 2
    for rid in ids:
        assert api.request("DELETE", f"/api/runs/{rid}", headers=JSON).status_code == 200, rid
    assert stores.list_runs() == []
    assert len(list((home() / "trash" / "logs").iterdir())) == 1  # the eval's log, kept
    assert api.request("DELETE", "/api/runs/m-nope", headers=JSON).status_code == 404


def test_a_job_that_ended_goes_to_the_trash_and_a_running_one_stays() -> None:
    jobs = Jobs(work=False)
    jobs.record(Job(id="20261005-000000-bbbb", title="t", argv=["x"], status="running"))
    with pytest.raises(HTTPException, match="cancel it first"):
        jobs.delete("20261005-000000-bbbb")
    jobs.record(Job(id="20261005-000000-aaaa", title="t", argv=["x"], status="succeeded"))
    gone = client().request("DELETE", "/api/launch/jobs/20261005-000000-aaaa", headers=JSON)
    assert gone.status_code == 200
    assert "20261005-000000-aaaa" not in [j.id for j in jobs.list()]
    assert len(list((home() / "trash" / "jobs").iterdir())) == 1

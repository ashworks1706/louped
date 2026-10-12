"""Requests for louped itself: kept as drafts here, filed through GitHub's prefilled issue form."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_agent import call, tools

from louped import __version__
from louped.core.paths import home
from louped.server import create_app


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "louped.toml").write_text("# my project\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def test_a_draft_is_kept_edited_opened_and_trashed(project: Path) -> None:
    api = client()
    assert api.get("/api/feedback").json() == []
    fields = {"problem": "Two checkpoints' graphs", "prebuilt": "circuit-tracer"}
    body = {"kind": "feature", "title": "Compare circuits", "fields": fields}
    made = api.post("/api/feedback", json=body).json()
    assert made["opened"] is None
    assert (home() / "feedback" / f"{made['id']}.json").is_file()

    url = urlsplit(made["issue_url"])
    asked = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "github.com" and url.path == "/ashworks1706/louped/issues/new"
    assert asked == {"template": "feature.yml", "title": "Compare circuits",
                     "problem": "Two checkpoints' graphs",
                     "prebuilt": f"circuit-tracer\n\nlouped {__version__}"}  # fmt: skip

    bug = {"kind": "bug", "title": "Crash", "fields": {"what": "It crashed"}}
    edited = api.put(f"/api/feedback/{made['id']}", json=bug)
    assert edited.json()["kind"] == "bug" and "template=bug.yml" in edited.json()["issue_url"]
    wrong = api.put(f"/api/feedback/{made['id']}",
                    json={"kind": "bug", "title": "Crash", "fields": {"problem": "x"}})  # fmt: skip
    assert wrong.status_code == 400 and "no field problem" in wrong.json()["detail"]

    long = {**bug, "fields": {"what": "x " * 5000}}  # GitHub refuses a link this long
    too_long = api.put(f"/api/feedback/{made['id']}", json=long)
    assert too_long.status_code == 400 and "too long" in too_long.json()["detail"]

    assert api.post(f"/api/feedback/{made['id']}/opened").status_code == 415  # not JSON
    assert api.post(f"/api/feedback/{made['id']}/opened", json={}).json()["opened"]
    assert api.delete(f"/api/feedback/{made['id']}").status_code == 200
    assert api.get("/api/feedback").json() == []
    assert list((home() / "trash" / "feedback").iterdir())
    assert api.put("/api/feedback/nope", json=body).status_code == 404
    assert api.delete("/api/feedback/../x").status_code == 404


def test_the_forms_match_the_repositorys_issue_forms(project: Path) -> None:
    forms = {f["kind"]: f for f in client().get("/api/feedback/forms").json()}
    root = Path(__file__).parents[1] / ".github" / "ISSUE_TEMPLATE"
    for form in forms.values():
        text = (root / form["template"]).read_text()
        for field in form["fields"]:
            assert f"id: {field['id']}" in text and f"label: {field['label']}" in text


def test_a_shared_server_keeps_no_drafts(project: Path) -> None:
    api = client(launching=False)
    assert api.post("/api/feedback", json={"kind": "bug", "title": "x"}).status_code == 403
    assert api.get("/api/feedback").status_code == 403


def test_an_agent_drafts_and_the_person_files_it(project: Path) -> None:
    mcp = tools()
    made = call(mcp, "draft_feedback", kind="feature", title="Sweep layers",
                problem="Find the best steering layer")  # fmt: skip
    assert made["page"] == f"/feedback/?id={made['id']}" and made["opened"] is None
    [listed] = call(mcp, "feedback")
    assert listed["title"] == "Sweep layers" and "problem=Find" in listed["issue_url"]

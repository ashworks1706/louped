"""Notes on any part of the app's pages: one file each in the project, read anywhere."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_agent import call, tools

from louped.core.paths import home
from louped.server import create_app
from louped.server.parts import ADDRESS
from louped.stores import notes


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "louped.toml").write_text("# my project\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


ROW = {"part": "items/row/28", "url": "/run/?id=m-1&tab=items", "run": "m-1",
       "shows": "28 yes no", "data": {"baseline": {"answer": "yes"}}}  # fmt: skip
LASSO = {"part": "figures/figure/scores.json", "url": "/run/?id=m-2&tab=figures", "run": "m-2",
         "data": {"points": [{"x": 1, "y": 2, "id": "7"}], "items": ["7"]}}  # fmt: skip


def test_a_note_is_kept_in_the_project_filtered_edited_and_trashed(project: Path) -> None:
    api = client()
    assert api.get("/api/notes").json() == []
    made = api.post("/api/notes", json={"text": "Caves *here*", "anchors": [ROW]}).json()
    assert made["by"] == "person" and made["anchors"][0]["data"] == ROW["data"]
    assert (project / "notes" / f"{made['id']}.json").is_file()  # beside experiments/, for git
    other = api.post("/api/notes", json={"text": "Cluster", "anchors": [LASSO, ROW]}).json()

    assert [n["id"] for n in api.get("/api/notes").json()] == [other["id"], made["id"]]
    assert [n["id"] for n in api.get("/api/notes", params={"run": "m-2"}).json()] == [other["id"]]
    on_rows = api.get("/api/notes", params={"part": "items/row"}).json()
    assert {n["id"] for n in on_rows} == {made["id"], other["id"]}
    assert api.get("/api/notes", params={"part": "items/ro"}).json() == []  # whole segments

    edited = api.put(f"/api/notes/{made['id']}", json={"text": "Caves at 28"}).json()
    assert edited["text"] == "Caves at 28" and edited["anchors"] == made["anchors"]
    assert edited["updated"] > made["updated"]
    assert api.get(f"/api/notes/{made['id']}").json()["text"] == "Caves at 28"

    assert api.delete(f"/api/notes/{made['id']}").status_code == 200
    assert [n["id"] for n in api.get("/api/notes").json()] == [other["id"]]
    assert list((home() / "trash" / "notes").iterdir())
    assert api.get(f"/api/notes/{made['id']}").status_code == 404
    assert api.delete("/api/notes/../x").status_code == 404


def test_a_note_names_real_parts_and_pages_and_stays_small(project: Path) -> None:
    api = client()
    for anchor in ({**ROW, "part": "Not An Address"}, {**ROW, "url": "https://x.y/run/"},
                   {**ROW, "url": "//x.y/"}):  # fmt: skip
        assert api.post("/api/notes", json={"text": "x", "anchors": [anchor]}).status_code == 422
    assert api.post("/api/notes", json={"text": "", "anchors": [ROW]}).status_code == 422
    assert api.post("/api/notes", json={"text": "x", "anchors": []}).status_code == 422
    big = {**LASSO, "data": {"points": [{"x": i, "y": i} for i in range(20_000)]}}
    too_big = api.post("/api/notes", json={"text": "x", "anchors": [big]})
    assert too_big.status_code == 413 and "over 200000" in too_big.json()["detail"]
    assert notes.ADDRESS.pattern == ADDRESS.pattern


def test_a_shared_server_shows_notes_and_writes_none(project: Path) -> None:
    made = client().post("/api/notes", json={"text": "x", "anchors": [ROW]}).json()
    shared = client(launching=False)
    assert [n["id"] for n in shared.get("/api/notes").json()] == [made["id"]]
    assert shared.post("/api/notes", json={"text": "x", "anchors": [ROW]}).status_code == 403
    assert shared.put(f"/api/notes/{made['id']}", json={"text": "y"}).status_code == 403
    assert shared.delete(f"/api/notes/{made['id']}").status_code == 403


def test_an_agent_reads_the_persons_notes_and_leaves_its_own(project: Path) -> None:
    client().post("/api/notes", json={"text": "Odd cluster", "anchors": [LASSO]})
    mcp = tools()
    [theirs] = call(mcp, "notes", run="m-2")
    assert theirs["by"] == "person" and theirs["anchors"][0]["data"]["items"] == ["7"]
    mine = call(mcp, "add_note", text="Item 7 is a parse failure", part="items/row/7",
                url="/run/?id=m-2&tab=items", run="m-2")  # fmt: skip
    assert mine["by"] == "agent" and mine["page"] == f"/notes/?id={mine['id']}"
    assert len(call(mcp, "notes", part="items/row")) == 1
    assert call(mcp, "edit_note", id=mine["id"], text="Parse failure")["text"] == "Parse failure"
    assert call(mcp, "delete_note", id=mine["id"]) == {"deleted": mine["id"]}
    assert [n["id"] for n in call(mcp, "notes")] == [theirs["id"]]

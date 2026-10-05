"""The app's pages as data: layouts from presets, the project and an experiment, checked before
they are used; the theme from louped.toml; the block a person points at, for their agent; and
the kit plugin pages draw with."""

import asyncio
import io
import json
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from louped.agent import server
from louped.server import create_app

JSON = {"content-type": "application/json"}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "louped.toml").write_text("")
    folder = tmp_path / "experiments" / "q"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("---\ndomain: honesty\nstatus: active\n---\n# q\n")
    panel = tmp_path / "plugins" / "verdicts" / "panel"
    panel.mkdir(parents=True)
    (tmp_path / "plugins" / "verdicts" / "plugin.toml").write_text('title = "Verdicts"\n')
    (panel / "run.html").write_text("<p>a run</p>")
    (panel / "card.html").write_text("<p>a card</p>")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def blocks(page: dict, region: str) -> list[str]:
    return [
        b["block"] if b["block"] != "plugin" else f"x-{b['plugin']}"
        for b in page["regions"][region]
    ]


def test_the_default_is_todays_pages_with_a_tab_for_each_plugin(project: Path) -> None:
    page = client().get("/api/ui/layout").json()
    assert blocks(page, "run.tabs") == ["overview", "items", "figures", "samples", "log",
                                        "artifacts", "config", "x-verdicts"]  # fmt: skip
    assert set(page["sources"].values()) == {"default"} and page["errors"] == []
    assert page["files"] == ["layout.json"]
    exposed = client(launching=False).get("/api/ui/layout").json()
    assert "x-verdicts" not in blocks(exposed, "run.tabs")  # plugins are off there


def test_an_experiments_layout_over_the_projects_over_a_preset(project: Path) -> None:
    (project / "layout.json").write_text(json.dumps({
        "preset": "eval",
        "regions": {"run.overview": [{"block": "metrics"}, {"block": "provenance"}]},
    }))  # fmt: skip
    (project / "experiments" / "q" / "layout.json").write_text(json.dumps({
        "regions": {"run.overview": [{"block": "file", "path": "examples.md", "title": "Examples"}]}
    }))  # fmt: skip
    api = client()
    page = api.get("/api/ui/layout").json()
    assert blocks(page, "run.overview") == ["metrics", "provenance"]
    assert blocks(page, "run.tabs")[0] == "items"  # the eval preset opens on items
    assert page["sources"]["run.tabs"] == "preset eval"
    assert page["sources"]["home"] == "default"
    q = api.get("/api/ui/layout", params={"experiment": "q"}).json()
    assert q["regions"]["run.overview"][0]["title"] == "Examples"
    assert q["sources"]["run.overview"] == "experiments/q/layout.json"
    assert q["files"] == ["layout.json", "experiments/q/layout.json"]
    # a run whose experiment is gone gets the project's
    gone = api.get("/api/ui/layout", params={"experiment": "gone"}).json()
    assert gone["sources"]["run.overview"] == "layout.json"


def test_a_layout_that_does_not_check_says_why_and_is_not_used(project: Path) -> None:
    (project / "layout.json").write_text(json.dumps({
        "preset": "loud",
        "regions": {"run.overview": [
            {"block": "metric"}, {"block": "chart"},
            {"block": "plugin", "plugin": "verdicts", "page": "nope.html"},
        ]},
    }))  # fmt: skip
    page = client().get("/api/ui/layout").json()
    assert set(page["sources"].values()) == {"default"}
    assert page["errors"] == [
        "layout.json: preset 'loud' is not one of eval, training, focus, default",
        "layout.json: run.overview[0]: metric needs key",
        "layout.json: run.overview[1]: 'chart' is not a block of run.overview: error, metrics, "
        "metric, history, hardware, report, file, figure, provenance, text, plugin",
        "layout.json: run.overview[2]: plugins/verdicts/panel/nope.html does not exist",
    ]
    (project / "layout.json").write_text('{"regions": {"run.overview": [{"block": 1}]}}')
    [error] = client().get("/api/ui/layout").json()["errors"]
    assert error.startswith("layout.json: ('regions', 'run.overview', 0, 'block')")


def test_a_region_and_a_preset_are_set_checked_and_cleared(project: Path) -> None:
    api = client()
    card = {"block": "plugin", "plugin": "verdicts", "page": "card.html", "width": "half"}
    body = {"region": "run.overview", "blocks": [{"block": "metric", "key": "accuracy"}, card]}
    assert api.put("/api/ui/layout", json=body).status_code == 200
    saved = json.loads((project / "layout.json").read_text())
    assert saved == {"regions": {"run.overview": [
        {"block": "metric", "key": "accuracy"},
        {"block": "plugin", "width": "half", "plugin": "verdicts", "page": "card.html"},
    ]}}  # fmt: skip
    bad = api.put("/api/ui/layout", json={"region": "home", "blocks": [{"block": "metrics"}]})
    assert bad.status_code == 422 and "'metrics' is not a block of home" in bad.json()["detail"]
    q = api.put("/api/ui/preset", json={"preset": "training", "experiment": "q"}).json()
    assert q["sources"]["run.tabs"] == "preset training"
    assert q["sources"]["run.overview"] == "layout.json"  # a set region stays over the preset
    api.put("/api/ui/preset", json={"preset": None, "experiment": "q"})
    assert not (project / "experiments" / "q" / "layout.json").exists()  # nothing left in it
    api.put("/api/ui/layout", json={"region": "run.overview", "blocks": None})
    assert not (project / "layout.json").exists()
    assert api.put("/api/ui/preset", json={"preset": "x", "experiment": "nope"}).status_code == 404
    assert client(launching=False).put("/api/ui/layout", json=body).status_code == 403
    assert api.put("/api/ui/layout", content=json.dumps(body)).status_code == 415


def test_the_theme_takes_tokens_and_plain_values_only(project: Path) -> None:
    (project / "louped.toml").write_text(
        'radius = 1\n[theme]\nradius = "0.25rem"\nfont = "x"\n'
        '[theme.light]\nintervention = "oklch(0.6 0.2 300)"\nsidebar = "red"\n'
        '[theme.dark]\nbackground = "red; } body { display: none"\n'
    )
    theme = client().get("/api/ui/theme").json()
    assert theme["light"] == {"radius": "0.25rem", "intervention": "oklch(0.6 0.2 300)"}
    assert theme["dark"] == {"radius": "0.25rem"}
    assert len(theme["errors"]) == 3 and "font" in theme["errors"][0]


def test_default_undoes_a_preset_and_bad_files_are_named(project: Path) -> None:
    (project / "layout.json").write_text('{"preset": "eval"}')
    q = project / "experiments" / "q" / "layout.json"
    q.write_text('{"preset": "default"}')  # this experiment wants no preset
    api = client()
    page = api.get("/api/ui/layout", params={"experiment": "q"}).json()
    assert set(page["sources"].values()) == {"default"} and page["errors"] == []
    # a folder without a README is not an experiment: its layout.json is not read or written
    bare = project / "experiments" / "bare"
    bare.mkdir()
    (bare / "layout.json").write_text('{"preset": "focus"}')
    page = api.get("/api/ui/layout", params={"experiment": "bare"}).json()
    assert page["files"] == ["layout.json"] and page["sources"]["run.tabs"] == "preset eval"
    assert (
        api.put("/api/ui/preset", json={"preset": "eval", "experiment": "bare"}).status_code == 404
    )
    q.write_bytes(b"\xff\xfe{")
    [error] = api.get("/api/ui/layout", params={"experiment": "q"}).json()["errors"]
    assert error.startswith("experiments/q/layout.json: cannot be read")
    q.write_text('{"regions": {"run.tabs": [{"block": "items"}, {"block": "items"}]}}')
    page = api.get("/api/ui/layout", params={"experiment": "q"}).json()
    assert page["errors"] == ["experiments/q/layout.json: run.tabs[1]: the same tab as run.tabs[0]"]


def test_a_theme_that_is_not_a_table_or_loads_a_url_is_dropped(project: Path) -> None:
    (project / "louped.toml").write_text('theme = "dark"\n')
    assert client().get("/api/ui/theme").json()["errors"] == [
        "louped.toml theme: not a [theme] table"
    ]
    (project / "louped.toml").write_text('[theme]\nradius = "url(https://x/y)"\n')
    theme = client().get("/api/ui/theme").json()
    assert theme["light"] == theme["dark"] == {}
    assert theme["errors"] == [
        "louped.toml [theme] radius: 'url(https://x/y)' is not a plain CSS value"
    ]


def call(mcp: MCPServer, tool: str, args: dict) -> object:
    result = asyncio.run(mcp.call_tool(tool, args))
    assert isinstance(result, CallToolResult) and not result.is_error, result
    text = result.content[0]
    assert isinstance(text, TextContent)
    return json.loads(text.text)


def test_a_person_picks_parts_and_their_agent_reads_them(project: Path) -> None:
    app = create_app(launching=True)
    api = TestClient(app, base_url="http://localhost")
    assert api.get("/api/ui/selection").json() is None
    row = {"id": "items/row/28", "url": "/run/?id=m-1&tab=items", "run": "m-1", "text": "28",
           "data": {"qid": "28", "records": {"baseline": {"pred": "True"}}}}  # fmt: skip
    stat = {**row, "id": "items/stat/pressure", "data": {"k": 1, "n": 2}}
    picked = {"parts": [row, stat]}
    assert api.post("/api/ui/selection", json=picked, headers=JSON).status_code == 200
    mcp = server("http://localhost", transport=httpx.ASGITransport(app=app))
    got = call(mcp, "ui_selection", {})
    assert [p["id"] for p in got["parts"]] == ["items/row/28", "items/stat/pressure"]  # type: ignore[index]
    assert got["parts"][0]["data"]["records"]["baseline"]["pred"] == "True"  # type: ignore[index]
    page = call(mcp, "ui_page", {"experiment": "q"})
    assert {"regions", "sources", "presets", "files", "errors", "parts"} <= set(page)  # type: ignore[arg-type]
    assert any(k["part"] == "items/row/*" for k in page["parts"])  # type: ignore[index]
    done = call(mcp, "set_layout", {"region": "run.overview", "blocks": [{"block": "metrics"}],
                                    "experiment": "q"})  # fmt: skip
    assert done["sources"]["run.overview"] == "experiments/q/layout.json"  # type: ignore[index]
    bad = api.post("/api/ui/selection", json={"parts": [{**row, "id": "Not An Address"}]})
    assert bad.status_code == 422
    big = {"parts": [{**row, "data": "x" * 150_000}, {**row, "data": "x" * 150_000}]}
    assert api.post("/api/ui/selection", json=big).status_code == 413
    assert client(launching=False).post("/api/ui/selection", json=picked).status_code == 403


def test_parts_are_changed_by_address_and_checked(project: Path) -> None:
    from louped.server.parts import kind_of

    assert kind_of("run/delete").part == "run/delete"  # type: ignore[union-attr]
    assert kind_of("run/title").part == "run/title"  # type: ignore[union-attr]
    assert kind_of("item/field/*/abstain").part == "item/field/*/*"  # type: ignore[union-attr]
    assert kind_of("items/nope/a/b/c") is None
    api = client()
    set_ = {"part": "item/field/*/abstain", "rule": {"hidden": True}, "experiment": "q"}
    page = api.put("/api/ui/part", json=set_).json()
    assert page["parts"]["item/field/*/abstain"]["hidden"] is True
    saved = json.loads((project / "experiments" / "q" / "layout.json").read_text())
    assert saved == {"parts": {"item/field/*/abstain": {"hidden": True}}}
    # the experiment's rule over the project's for the same key; the project's elsewhere
    api.put("/api/ui/part", json={"part": "item/field/*/abstain", "rule": {"label": "abs"}})
    api.put("/api/ui/part", json={"part": "items/show", "rule": {"default": "changed"}})
    q = api.get("/api/ui/layout", params={"experiment": "q"}).json()["parts"]
    assert q["item/field/*/abstain"]["hidden"] and q["item/field/*/abstain"]["label"] is None
    assert q["items/show"]["default"] == "changed"
    wrong = api.put("/api/ui/part", json={"part": "items/row/28", "rule": {"label": "x"}})
    assert wrong.status_code == 422
    assert "label does not apply; it takes nothing" in wrong.json()["detail"]
    unknown = api.put("/api/ui/part", json={"part": "items/rows/28", "rule": {"hidden": True}})
    assert "not a part's address" in unknown.json()["detail"]
    empty = api.put("/api/ui/part", json={"part": "run/delete", "rule": {}})
    assert "changes nothing" in empty.json()["detail"]
    gone = {"part": "item/field/*/abstain", "rule": None, "experiment": "q"}
    api.put("/api/ui/part", json=gone)
    assert api.put("/api/ui/part", json=gone).status_code == 404  # nothing to remove: said
    assert not (project / "experiments" / "q" / "layout.json").exists()


def test_the_agent_shows_the_person_a_part_and_hears_what_was_missing(project: Path) -> None:
    app = create_app(launching=True)
    mcp = server("http://localhost", transport=httpx.ASGITransport(app=app))

    async def app_open() -> None:
        """What the open app does: reads new cues and says which parts it found."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as web:
            for _ in range(40):
                await asyncio.sleep(0.1)
                cues = (await web.get("/api/ui/show", params={"after": 0})).json()["cues"]
                if cues:
                    await web.post(
                        f"/api/ui/show/{cues[0]['id']}/seen", json={"missing": ["items/row/404"]}
                    )
                    return

    async def both() -> object:
        args = {"url": "/run/?id=m-1&tab=items", "parts": ["items/row/28", "items/row/404"],
                "text": "Pressure flipped this one.", "style": "spotlight"}  # fmt: skip
        result, _ = await asyncio.gather(mcp.call_tool("ui_show", args), app_open())
        assert isinstance(result, CallToolResult) and not result.is_error, result
        assert isinstance(result.content[0], TextContent)
        return json.loads(result.content[0].text)

    cue = asyncio.run(both())
    assert cue["status"] == "shown" and cue["missing"] == ["items/row/404"]  # type: ignore[index]
    api = TestClient(app, base_url="http://localhost")
    bad = api.post("/api/ui/show", json={"parts": ["Bad Address"]}, headers=JSON)
    assert bad.status_code == 422
    for off_site in ("https://x", "//x.example/y", "/\\x.example"):  # a path on this app only
        assert api.post("/api/ui/show", json={"url": off_site}).status_code == 422
    # a newer cue before the app found this one's parts
    later = api.post("/api/ui/show", json={"parts": ["run/title"]}).json()
    api.post(f"/api/ui/show/{later['id']}/seen", json={"superseded": True})
    assert api.get(f"/api/ui/show/{later['id']}").json()["status"] == "superseded"
    assert client(launching=False).post("/api/ui/show", json={}).status_code == 403


def test_the_apps_tests_know_every_kind_of_part() -> None:
    """apps/web/e2e/part-kinds.json, which the app's tests check its addresses against, is this
    server's catalog."""
    from louped.server.parts import KINDS

    file = Path(__file__).parents[1] / "apps" / "web" / "e2e" / "part-kinds.json"
    assert json.loads(file.read_text()) == [k.model_dump() for k in KINDS]


def test_plugin_pages_get_the_kit() -> None:
    api = client(launching=False)
    assert ".l-stat" in api.get("/kit/louped.css").text
    assert "export function stats" in api.get("/kit/louped.js").text


def test_the_apps_tests_use_the_servers_default(project: Path) -> None:
    """apps/web/e2e/default-layout.json, which the app's tests serve, is this server's default."""
    from louped.server.ui import page

    file = Path(__file__).parents[1] / "apps" / "web" / "e2e" / "default-layout.json"
    assert json.loads(file.read_text()) == page(None, None).model_dump(exclude_none=True)


def test_picks_reach_the_agent_with_its_next_message(project: Path, monkeypatch, capsys) -> None:
    from louped import cli
    from louped.picks import asked, for_prompt

    assert (asked("why?"), asked("@sel why?"), asked("@sel 2 vs @sel 1,3")) == (None, [], [1, 2, 3])
    assert asked("mail@self.org") is None and asked("@selection") is None
    app = create_app(launching=True)
    api = cast(httpx.Client, TestClient(app, base_url="http://localhost/api"))  # one, in effect
    assert for_prompt(api, "hi") is None  # nothing picked: nothing added
    assert (
        for_prompt(api, "@sel") == "The message says @sel, but nothing is picked in louped's app."
    )
    row = {"id": "items/row/28", "url": "/run/?id=m-1&tab=items", "run": "m-1", "text": "28",
           "data": {"qid": "28"}}  # fmt: skip
    stat = {**row, "id": "items/stat/pressure", "text": "31%", "data": {"k": 5, "n": 16}}
    got = api.post("/ui/selection", json={"parts": [row, stat]}, headers=JSON).json()
    assert (got["version"], got["read"]) == (1, 0)

    # new picks arrive with the next message, once; @sel asks again, all or by number
    first = for_prompt(api, "why did this flip?")
    assert first and "pick 1: louped part items/row/28" in first and "pick 2:" in first
    assert '"qid": "28"' in first and "run: m-1" in first
    assert api.get("/ui/selection").json()["read"] == 1  # the tray now says the agent read them
    assert for_prompt(api, "and now?") is None
    second = for_prompt(api, "compare @sel 2")
    assert (
        second and "pick 2: louped part items/stat/pressure" in second and "pick 1:" not in second
    )
    assert (
        for_prompt(api, "@sel 3") == "The message asks for pick 3, but the tray holds picks 1 to 2."
    )
    assert api.post("/ui/selection/read", json={"version": 9}, headers=JSON).status_code == 404

    # as Claude Code calls it: the prompt on stdin, the context on stdout
    monkeypatch.setattr(httpx, "Client", lambda **kw: TestClient(app, base_url=kw["base_url"]))
    api.post("/ui/selection", json={"parts": [row]}, headers=JSON)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "look"})))
    cli._picks(cli.Picks(hook=True))
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit" and "items/row/28" in out["additionalContext"]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "look again"})))
    cli._picks(cli.Picks(hook=True))
    assert capsys.readouterr().out == ""  # already read: nothing added


def test_picks_without_the_app(monkeypatch) -> None:
    from louped.picks import for_prompt

    down = httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(
        httpx.ConnectError("refused"))), base_url="http://localhost/api")  # fmt: skip
    assert for_prompt(down, "hi") is None
    said = for_prompt(down, "@sel")
    assert said and said.startswith("The message says @sel, but louped's app at")

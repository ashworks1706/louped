"""The app's pages as data: layouts from presets, the project and an experiment, checked before
they are used; the theme from louped.toml; the block a person points at, for their agent; and
the kit plugin pages draw with."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
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


def test_a_person_points_at_a_block_and_their_agent_reads_which(project: Path) -> None:
    app = create_app(launching=True)
    api = TestClient(app, base_url="http://localhost")
    assert api.get("/api/ui/selection").json() is None
    picked = {"id": "run.overview/metrics/accuracy", "url": "/run/?id=m-1", "run": "m-1",
              "text": "accuracy 0.62"}  # fmt: skip
    assert api.post("/api/ui/selection", json=picked, headers=JSON).status_code == 200
    mcp = server("http://localhost", transport=httpx.ASGITransport(app=app))

    def call(tool: str, args: dict) -> object:
        result = asyncio.run(mcp.call_tool(tool, args))
        assert isinstance(result, CallToolResult) and not result.is_error, result
        text = result.content[0]
        assert isinstance(text, TextContent)
        return json.loads(text.text)

    assert call("ui_selection", {})["id"] == "run.overview/metrics/accuracy"  # type: ignore[index]
    page = call("ui_page", {"experiment": "q"})
    assert {"regions", "sources", "presets", "files", "errors"} <= set(page)  # type: ignore[arg-type]
    done = call("set_layout", {"region": "run.overview", "blocks": [{"block": "metrics"}],
                               "experiment": "q"})  # fmt: skip
    assert done["sources"]["run.overview"] == "experiments/q/layout.json"  # type: ignore[index]
    assert client(launching=False).post("/api/ui/selection", json=picked).status_code == 403


def test_plugin_pages_get_the_kit() -> None:
    api = client(launching=False)
    assert ".l-stat" in api.get("/kit/louped.css").text
    assert "export function stats" in api.get("/kit/louped.js").text


def test_the_apps_tests_use_the_servers_default(project: Path) -> None:
    """apps/web/e2e/default-layout.json, which the app's tests serve, is this server's default."""
    from louped.server.ui import page

    file = Path(__file__).parents[1] / "apps" / "web" / "e2e" / "default-layout.json"
    assert json.loads(file.read_text()) == page(None, None).model_dump(exclude_none=True)

"""A project's plugins: routes, a panel, a command and agent tools, without a louped release."""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from louped.agent import server
from louped.cli import _plugin_command
from louped.server import create_app

CODE = '''
from fastapi import APIRouter

router = APIRouter()
VERDICTS = {"1": "right"}


@router.get("/verdicts")
def verdicts() -> dict[str, str]:
    return VERDICTS


def main(argv: list[str]) -> None:
    print("verdicts", *argv)


def tools(mcp, api) -> None:
    @mcp.tool()
    async def verdicts() -> dict:
        """The verdicts given so far."""
        return (await api.get("/x/verdicts/verdicts")).json()
'''


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "louped.toml").write_text("")
    folder = tmp_path / "plugins" / "verdicts"
    (folder / "panel").mkdir(parents=True)
    (folder / "plugin.toml").write_text('title = "Verdicts"\nsection = "behavior"\n')
    (folder / "plugin.py").write_text(CODE)
    (folder / "panel" / "index.html").write_text("<p>verdicts</p>")
    monkeypatch.chdir(tmp_path)
    for name in [m for m in sys.modules if m.startswith("louped_plugin_")]:
        monkeypatch.delitem(sys.modules, name)
    return tmp_path


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def test_a_plugin_adds_routes_and_a_panel_only_where_launching_is_on(project: Path) -> None:
    api = client()
    [plugin] = api.get("/api/plugins").json()
    assert plugin == {"name": "verdicts", "title": "Verdicts", "section": "behavior",
                      "description": "", "panel": True, "error": None}  # fmt: skip
    assert api.get("/api/x/verdicts/verdicts").json() == {"1": "right"}
    assert api.get("/x/verdicts/").text == "<p>verdicts</p>"
    exposed = client(launching=False)
    assert exposed.get("/api/plugins").json() == []
    assert exposed.get("/x/verdicts/").status_code == 404


def test_a_plugin_that_does_not_load_says_why(project: Path) -> None:
    (project / "plugins" / "verdicts" / "plugin.py").write_text("raise RuntimeError('typo')\n")
    [plugin] = client().get("/api/plugins").json()
    assert "RuntimeError: typo" in plugin["error"]


def test_a_plugin_adds_a_command_and_agent_tools(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["louped", "verdicts", "--all"])
    assert _plugin_command()
    assert capsys.readouterr().out == "verdicts --all\n"
    monkeypatch.setattr(sys, "argv", ["louped", "serve"])
    assert not _plugin_command()  # louped's own commands stay louped's

    mcp = server("http://localhost", transport=httpx.ASGITransport(app=create_app(launching=True)))
    result = asyncio.run(mcp.call_tool("verdicts", {}))
    assert not result.is_error
    found = result.structured_content or json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert found.get("result", found) == {"1": "right"}

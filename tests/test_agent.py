"""The MCP server for coding agents, against the real app through ASGI."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_stores import run_eval, write_experiment

from loupe.agent import server
from loupe.server import create_app


def tools(launching: bool = True):
    app = create_app(launching=launching)
    return server("http://localhost", transport=httpx.ASGITransport(app=app))


def call(mcp, tool: str, /, **args: Any) -> Any:
    result = asyncio.run(mcp.call_tool(tool, args))
    assert not result.is_error, result.content
    if result.structured_content is not None:
        found = result.structured_content
        return found.get("result", found) if set(found) == {"result"} else found
    return json.loads(result.content[0].text)


def test_an_agent_reads_experiments_runs_samples_and_compares(tmp_path: Path) -> None:
    write_experiment(tmp_path, "pressure", "honesty", "active")
    run_eval(["yes", "no"], tags=["experiment:pressure"])
    run_eval(["yes", "yes"], tags=["experiment:pressure"])
    mcp = tools()
    assert call(mcp, "status")["launching"] is True
    [e] = call(mcp, "experiments", axis="behavior", status="active")
    assert e["name"] == "pressure" and e["runs"] == 2 and e["question"] == "Does it cave?"
    assert call(mcp, "experiments", axis="efficiency") == []
    assert len(call(mcp, "experiment", name="pressure")["runs"]) == 2
    a, b = sorted(call(mcp, "runs", experiment="pressure"), key=lambda r: r["created"])
    assert a["kind"] == "eval" and a["metrics"]
    assert call(mcp, "runs", kind="training") == []
    assert call(mcp, "run", run_id=a["id"])["id"] == a["id"]
    [first] = call(mcp, "samples", run_id=a["id"], limit=1)
    whole = call(mcp, "sample", run_id=a["id"], sample_id=str(first["id"]))
    assert whole["id"] == first["id"] and whole["scores"]
    diff = call(mcp, "compare", a=a["id"], b=b["id"])
    assert diff["scores"] and diff["scores"][0]["n"] == 2


def test_an_agent_reads_a_runs_figures_one_at_a_time(tmp_path: Path) -> None:
    import mlflow

    from loupe.analysis.views import heatmap
    from loupe.tracking import log_json, start_run

    with start_run("lens", kind="analysis") as active:
        log_json(heatmap("lens", [[0.5]], ["0"], ["0"], "position", "layer", about="how"),
                 "views/00-lens.json")  # fmt: skip
        run_id = f"m-{active.info.run_id}"
    assert mlflow.active_run() is None
    mcp = tools()
    [f] = call(mcp, "figures", run_id=run_id)
    assert f == {"index": 0, "kind": "heatmap", "title": "lens", "about": "how", "note": None}
    assert call(mcp, "figure", run_id=run_id, index=0)["z"] == [[0.5]]
    with pytest.raises(ToolError, match=r"m-\w+ has 1 figures$"):
        asyncio.run(mcp.call_tool("figure", {"run_id": run_id, "index": 3}))


def test_an_agent_launches_follows_and_cancels_jobs_through_the_queue(tmp_path: Path) -> None:
    exp = tmp_path / "experiments" / "hello"
    exp.mkdir(parents=True)
    (exp / "README.md").write_text("---\ndomain: inference\nstatus: parked\n---\n# hello\n")
    (exp / "run.py").write_text(
        "import time\nfrom dataclasses import dataclass\n\nimport tyro\n\n\n@dataclass\n"
        'class Args:\n    name: str = "world"\n    wait: float = 0\n\n\n'
        'if __name__ == "__main__":\n    args = tyro.cli(Args)\n    time.sleep(args.wait)\n'
        '    assert args.name != "boom", "boom"\n    print("hello", args.name)\n'
    )
    mcp = tools()
    hello = "script:hello/run.py"
    assert hello in {x["id"] for x in call(mcp, "launchables")}
    opts = call(mcp, "launch_options", id=hello)
    assert [o["flag"] for o in opts["options"]] == ["--name", "--wait"] and opts["config"] is None
    done = call(mcp, "launch", id=hello, options={"--name": "agent"}, wait_seconds=60)
    assert done["status"] == "succeeded" and "hello agent" in done["log"]
    assert call(mcp, "jobs")[0]["id"] == done["id"]
    with pytest.raises(ToolError, match=r"failed:\n(.|\n)*AssertionError: boom"):
        asyncio.run(mcp.call_tool("launch", {"id": hello, "options": {"--name": "boom"},
                                             "wait_seconds": 60}))  # fmt: skip
    slow = call(mcp, "launch", id=hello, options={"--wait": "30"}, wait_seconds=1)
    assert slow["status"] == "running"
    assert call(mcp, "cancel_job", job_id=slow["id"])["status"] == "cancelled"
    made = call(mcp, "launch", id="new", options={"name": "my-q", "--domain": "honesty"},
                wait_seconds=120)  # fmt: skip
    assert made["status"] == "succeeded", made["log"]
    assert (tmp_path / "experiments" / "my-q" / "README.md").exists()


def test_an_exposed_server_refuses_an_agents_launch() -> None:
    mcp = tools(launching=False)
    with pytest.raises(ToolError, match="loupe answered 403: launching is off"):
        asyncio.run(mcp.call_tool("launch", {"id": "new"}))
    assert call(mcp, "status")["launching"] is False


def test_an_agent_is_told_when_no_server_is_running() -> None:
    mcp = server("http://127.0.0.1:9")
    with pytest.raises(ToolError, match=r"no loupe server at http://127\.0\.0\.1:9"):
        asyncio.run(mcp.call_tool("status", {}))


def test_loupe_mcp_speaks_mcp_over_stdio() -> None:
    import sys

    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def connect() -> tuple[set[str], str]:
        loupe = str(Path(sys.executable).with_name("loupe"))
        cmd = StdioServerParameters(command=loupe, args=["mcp", "--url", "http://127.0.0.1:9"])
        async with stdio_client(cmd) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            found = {t.name for t in (await session.list_tools()).tools}
            result = await session.call_tool("status", {})
            assert result.is_error
            return found, result.content[0].text  # type: ignore[union-attr]

    found, error = asyncio.run(connect())
    assert {"experiments", "runs", "figure", "compare", "launch", "job"} <= found
    assert "no loupe server at http://127.0.0.1:9" in error

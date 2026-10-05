"""louped for coding agents: an MCP server over a running `louped serve`.

It is a client of the same HTTP API the UI calls, so an agent sees what the UI sees and starts work
through the same job queue: one job at a time, shown live on Runs and on the job's page, and off on
a server started with --expose. It reads nothing on its own and keeps no state.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

#: How to use the tools, sent to the agent when it connects.
INSTRUCTIONS = """louped is a research testbed for language models: behavior (what models do and
the mechanisms behind it) and efficiency (what it costs to run them).

An experiment is a research question: a folder under experiments/ with a README (front matter
with domain and status, then Question, Observation, Hypotheses, Baseline, Test, Stop if, Run,
Result, Next) and its code: run.py (a tyro Args dataclass, the Launch form), task.py (Inspect
tasks), training and grid YAML. A run is one eval, analysis or training run an experiment wrote;
it has metrics, figures and, for an eval, samples. A job is a command started from the queue; its
runs appear as it writes them.

Work like this: read the experiments and runs first. Start a question with new_experiment, then
edit its README and run.py in the project (the project's AGENTS.md says what goes where). Start
work with launchables, launch_options and launch (a script is "script:<name>/run.py"); follow it
with job; read results with run, figures, figure, samples and compare. A run too large for this
machine goes to a cluster with export_job; its result comes back with import_result.
Report a difference only with its paired interval from compare, and name the run ids you used.
Jobs run one at a time on this machine's GPU, so do not queue more than the question needs."""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
STOP = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)


def server(url: str = "http://127.0.0.1:8000", transport: httpx.AsyncBaseTransport | None = None):
    """The MCP server for the louped API at url. transport replaces the network, for tests."""
    api = httpx.AsyncClient(base_url=f"{url.rstrip('/')}/api", transport=transport, timeout=180)
    mcp = MCPServer("louped", instructions=INSTRUCTIONS)

    async def send(method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await api.request(method, path, **kwargs)
        except httpx.ConnectError as e:
            raise ToolError(f"no louped server at {url}; start one with `louped serve`") from e
        except httpx.HTTPError as e:
            raise ToolError(f"{method} {path} to {url} failed: {e!r}") from e
        return _read(response)

    async def get(path: str, **params: Any) -> Any:
        return await send("GET", path, params={k: v for k, v in params.items() if v is not None})

    async def post(path: str, body: dict[str, Any]) -> Any:
        return await send("POST", path, json=body)

    @mcp.tool(annotations=READ)
    async def status() -> dict[str, Any]:
        """The server: its version, where it keeps runs, and whether it launches jobs."""
        return await get("/health")

    @mcp.tool(annotations=READ)
    async def experiments(
        axis: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Every research question: name, domain, status, question, result and run count. Filter
        by axis (behavior, efficiency, checks) or status (active, parked, answered)."""
        found = await get("/experiments")
        return [
            {**{k: e[k] for k in ("name", "axis", "domain", "status", "question", "result")},
             "runs": len(e["runs"])}
            for e in found
            if (axis is None or e["axis"] == axis) and (status is None or e["status"] == status)
        ]  # fmt: skip

    @mcp.tool(annotations=READ)
    async def experiment(name: str) -> dict[str, Any]:
        """One question: its README without the front matter, and the ids of its runs."""
        e = await get(f"/experiments/{name}")
        return {**e, "runs": [r["id"] for r in e["runs"]]}

    @mcp.tool(annotations=READ)
    async def runs(
        experiment: str | None = None, kind: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Runs, newest first: id, name, kind (eval, analysis, training), experiment, model,
        status and metrics. Filter by experiment or kind."""
        found = await get("/runs")
        keep = ("id", "name", "kind", "experiment", "model", "status", "created", "metrics")
        return [
            {k: r.get(k) for k in keep}
            for r in found
            if (experiment is None or r["experiment"] == experiment)
            and (kind is None or r["kind"] == kind)
        ][:limit]

    @mcp.tool(annotations=READ)
    async def run(run_id: str) -> dict[str, Any]:
        """One run in full: metrics, params, tags, the task and model, and any error."""
        return await get(f"/runs/{run_id}")

    @mcp.tool(annotations=READ)
    async def figures(run_id: str) -> list[dict[str, Any]]:
        """A run's figures by index: kind, title, how to read it and its note. Read one's data
        with figure."""
        found = await get(f"/runs/{run_id}/views")
        return [
            {"index": i, "kind": v["view"]["kind"], "title": v["view"]["title"],
             "about": v["view"].get("about"), "note": v["view"].get("note")}
            for i, v in enumerate(found)
        ]  # fmt: skip

    @mcp.tool(annotations=READ)
    async def figure(run_id: str, index: int) -> dict[str, Any]:
        """One figure's data: a heatmap's grid, a line's series, a table's rows."""
        found = await get(f"/runs/{run_id}/views")
        if not 0 <= index < len(found):
            raise ToolError(f"{run_id} has {len(found)} figures")
        return found[index]["view"]

    @mcp.tool(annotations=READ)
    async def samples(run_id: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """An eval's samples: id, input, target, the model's answer and its scores."""
        return (await get(f"/runs/{run_id}/samples"))[offset : offset + limit]

    @mcp.tool(annotations=READ)
    async def sample(run_id: str, sample_id: str, epoch: int = 1) -> dict[str, Any]:
        """One sample's whole transcript, with every score and its explanation."""
        return await get(f"/runs/{run_id}/samples/{sample_id}", epoch=epoch)

    @mcp.tool(annotations=READ)
    async def compare(a: str, b: str) -> dict[str, Any]:
        """Two eval runs over the same samples: each score's paired difference (b minus a) with
        its 95% bootstrap interval, and the samples that moved. a is the baseline."""
        return await get("/compare", a=a, b=b)

    @mcp.tool(annotations=READ)
    async def vectors() -> list[dict[str, Any]]:
        """Saved directions: name, model, layer, method (diff-in-means, logistic-probe,
        sae-decoder), norm and the run that made each."""
        return await get("/vectors")

    @mcp.tool(annotations=READ)
    async def launchables() -> list[dict[str, Any]]:
        """What can be started: experiment scripts, training configs, grids, data steps and
        louped's commands (new, sweep, features, circuit, grid, eval)."""
        found = await get("/launch")
        return [{k: x.get(k) for k in ("id", "group", "title", "description")} for x in found]

    @mcp.tool(annotations=READ)
    async def launch_options(id: str) -> dict[str, Any]:
        """A launchable's options (flag, kind, default, help) and, for a training config or
        grid, the config text to edit."""
        found = {x["id"]: x for x in await get("/launch")}
        if id not in found:
            raise ToolError(f"unknown launchable {id!r}; see launchables")
        return {"options": await get("/launch/options", id=id), "config": found[id]["config"],
                "recipe": found[id]["recipe"]}  # fmt: skip

    @mcp.tool(annotations=WRITE)
    async def launch(
        id: str,
        options: dict[str, str | bool | list[str]] | None = None,
        config: str | None = None,
        recipe: str | None = None,
        wait_seconds: int = 0,
    ) -> dict[str, Any]:
        """Queue a job. options maps a flag to its value, only those changed from the default; a
        positional argument goes under its name without dashes. config replaces a training or
        grid config's text; recipe picks sft, dpo, grpo, classify or reft for a training config.
        With wait_seconds, waits up to that long for the job to end and returns its log; a job
        still queued or running after that is returned as it stands. id "new" with name and
        --domain starts a research question under experiments/."""
        body = {"id": id, "options": options or {}, "config": config, "recipe": recipe}
        job = await post("/launch", body)
        return await _wait(job["id"], wait_seconds) if wait_seconds > 0 else job

    @mcp.tool(annotations=READ)
    async def jobs() -> list[dict[str, Any]]:
        """Every job, newest first, with its status."""
        found = await get("/launch/jobs")
        keep = ("id", "title", "status", "created", "started", "ended", "exit_code")
        return [{k: j.get(k) for k in keep} for j in found]

    @mcp.tool(annotations=READ)
    async def job(job_id: str) -> dict[str, Any]:
        """One job: its status, command line and the end of its log."""
        return await get(f"/launch/jobs/{job_id}")

    @mcp.tool(annotations=STOP)
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """Stop a queued or running job, and wait for it to end."""
        await post(f"/launch/jobs/{job_id}/cancel", {})
        return await _wait(job_id, 10)

    @mcp.tool(annotations=WRITE)
    async def new_experiment(name: str, domain: str) -> dict[str, Any]:
        """Start a research question: experiments/<name>/ with its README to fill in and a run.py
        to write, active. name is kebab-case, named for the question; domain is one the project's
        louped.toml lists (else louped's own: mechanisms, honesty, conditioning, agents, context,
        inference, specialisation, reproduction). Returns the finished job and its log."""
        body = {"id": "new", "options": {"name": name, "--domain": domain}}
        job = await post("/launch", body)
        return await _wait(job["id"], 60)

    @mcp.tool(annotations=WRITE)
    async def export_job(
        id: str,
        target: dict[str, Any],
        options: dict[str, str | bool | list[str]] | None = None,
        out_dir: str = ".",
    ) -> dict[str, Any]:
        """Package a launch to run on another machine, without running it here: job.sh for Sol, a
        Slurm cluster or a VM. id and options are as for launch; target holds provider (sol, slurm
        or shell), gpu, gpus, hours, cpus, partition, qos and constraint, the server filling in the
        rest. Saves it under out_dir and returns its path and a note: one file, louped-<job>.sh,
        when the project is a pushed git commit, else louped-<job>.tar.gz with job.sh inside. The
        person runs it there (`sbatch`, bash on a VM). With a remote set, its results come back
        with pull; else they bring back louped-result-<job>.tar.gz for import_result."""
        body = {"id": id, "options": options or {}, "target": target}
        try:
            response = await api.post("/launch/export", json=body)
        except httpx.HTTPError as e:
            raise ToolError(f"export to {url} failed: {e!r}") from e
        if not response.is_success:
            _read(response)
        found = re.search(r'filename="?([^";]+)"?', response.headers.get("content-disposition", ""))
        name = found.group(1) if found else "louped-job.tar.gz"
        path = Path(out_dir).expanduser().resolve() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return {"path": str(path), "bytes": len(response.content),
                "note": response.headers.get("x-louped-note", "")}  # fmt: skip

    @mcp.tool(annotations=WRITE)
    async def import_result(path: str) -> dict[str, Any]:
        """Add a louped-result-<job>.tar.gz (or its unpacked folder) from another machine to this
        louped: its runs join Runs marked with where they ran; importing twice adds nothing."""
        return await post("/launch/import-path", {"path": path})

    @mcp.tool(annotations=WRITE)
    async def push() -> dict[str, Any]:
        """Push the runs this louped made and has not pushed to the project's remote, as one new
        bundle there, so others (or another machine) can pull them."""
        return await post("/launch/push", {})

    @mcp.tool(annotations=WRITE)
    async def pull() -> list[dict[str, Any]]:
        """Add the runs pushed to the project's remote that this louped has not pulled, including
        the results of jobs exported from here; returns what each bundle added."""
        return await post("/launch/pull", {})

    async def _wait(job_id: str, seconds: int) -> dict[str, Any]:
        for _ in range(seconds * 2):
            found = await get(f"/launch/jobs/{job_id}")
            if found["status"] == "failed":
                raise ToolError(f"job {job_id} failed:\n{found['log']}")
            if found["status"] not in ("queued", "running"):
                return found
            await asyncio.sleep(0.5)
        return await get(f"/launch/jobs/{job_id}")

    return mcp


def _read(response: httpx.Response) -> Any:
    """The body, or the server's own message as the tool's error."""
    if response.is_success:
        return response.json()
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise ToolError(f"louped answered {response.status_code}: {detail}")

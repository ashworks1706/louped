"""louped for coding agents: an MCP server over a running `louped serve`.

It is a client of the same HTTP API the UI calls, so an agent sees what the UI sees and starts work
through the same job queue: one job at a time, shown live on Runs and on the job's page, and off on
a server started with --expose. It reads nothing on its own and keeps no state.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from louped.core.plugins import find_plugins

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
with job; read results with run, figures, figure, samples and compare; trace says where a figure's
mark or a record comes from (its rows, script and commit). Papers and docs the project rests
on are its sources: search_sources and source_page before the web, add_source to keep one.
A figure the person asks for (a chart of a file, points in 3D, an animation) is add_view, or
derive when it needs a script
over the run's files (new columns on its items); then ui_show. Evals are Inspect tasks: eval_tasks
lists the project's and inspect_evals' to launch with "eval". Judging two eval runs is launch
"judge" with --judge one of judges; a new criterion or prompt is new_judge. The person's own
blind picks of two runs (Compare's Blind A/B) are ab_results; check a judge against them there.
A run too large for this machine goes to a cluster, a VM or Colab with export_job; its result
comes back with pull or import_result. A run's code (run, trace) links its script at its commit.
Report a difference only with its paired interval from compare (or cohort, for a run's items),
and name the run ids you used. Items the person picks can be saved as a cohort and run again.
Jobs run one at a time on this machine's GPU, so do not queue more than the question needs.
The app's pages are data: ui_page shows them and every kind of part on them; ui_selection says
which parts the person Shift+clicked, with their data. Call it when they refer to something on
screen ("this row", "these", @sel 2); in Claude Code, new picks also arrive with their message.
set_layout, set_preset and set_part change the pages; ui_show opens a page and points the person
at parts, with a note."""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
#: Writes, and reaches the web when given a URL.
FETCH = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
STOP = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
#: Seconds ui_show waits for the app: a poll, the page opening, eight seconds of looking.
SHOW_WAIT = 15


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

    async def get(path: str, /, **params: Any) -> Any:
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
    async def sources() -> list[dict[str, Any]]:
        """The project's sources/: the papers, docs, slides and notebooks its claims rest on,
        each with its key (what a citation names), title, kind, origin URL and pages."""
        return await get("/sources")

    @mcp.tool(annotations=READ)
    async def search_sources(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """The pages of the project's sources holding every word of query, best first, each with
        its key, page and a snippet. Search here before going to the web."""
        return await get("/sources/search", q=query, limit=limit)

    @mcp.tool(annotations=READ)
    async def source_page(key: str, page: int) -> dict[str, Any]:
        """One page of a source's text, counted from 1: what to quote, word for word."""
        return await get(f"/sources/{quote(key, safe='')}/pages/{page}")

    @mcp.tool(annotations=READ)
    async def pins(key: str | None = None) -> list[dict[str, Any]]:
        """The passages pinned in the project's sources (of one source, or all), each with its
        quote, page, note and what it is linked to. Cite one as [@<key> p<page>]."""
        return await get("/pins", key=key)

    @mcp.tool(annotations=WRITE)
    async def pin(
        key: str, page: int, quote: str, note: str | None = None, links: list[str] | None = None
    ) -> dict[str, Any]:
        """Pin the passage a claim rests on: quote is the words exactly as source_page shows them
        (a paraphrase is refused), links what it bears on (a ref such as experiment:<name> or
        run:<id>, or a part's address). Then cite it in Markdown as [@<key> p<page>]: the app
        shows the quote when it is hovered."""
        return await post("/pins", {"key": key, "page": page, "quote": quote, "note": note,
                                    "links": links or []})  # fmt: skip

    @mcp.tool(annotations=FETCH)
    async def add_source(
        location: str, key: str | None = None, title: str | None = None
    ) -> dict[str, Any]:
        """Keep a paper, doc, deck or notebook in the project's sources/ so it can be searched,
        quoted and cited: a file in the project (copy one from elsewhere in first), or an https
        URL (an arXiv page, a shared Google Doc or Slides deck, a notebook on GitHub or opened
        from GitHub in Colab, a direct file link). Fetch a paper only from its primary source;
        the URL is recorded with the file."""
        return await post("/sources", {"location": location, "key": key, "title": title})

    @mcp.tool(annotations=READ)
    async def trace(ref: str) -> dict[str, Any]:
        """Where a piece of evidence comes from, from it down to the run: a figure, the derive
        script that made it and its commit, an item's record in every file that holds it, and
        the run with its commit (code: its script's page at that commit on GitHub, GitLab or
        Bitbucket, dirty, pushed). ref is run:<run id>[/<path>][#<item>], such as a figure's mark
        run:m-1/views/umap.json#17, or experiment:<name>/views/<figure>.json[#<item>]."""
        return await get("/trace", ref=ref)

    @mcp.tool(annotations=READ)
    async def reports() -> list[dict[str, Any]]:
        """The files in the project's reports/: Markdown write-ups, decks (.pptx), documents
        (.docx), PDFs and exported figures, each figure with the ref it was exported from.
        Each has the experiment it reports on (its front matter's experiment:, else its first
        folder when that is an experiment, else the one experiment its refs point to; null when
        none) and the runs its refs cite."""
        return await get("/reports")

    @mcp.tool(annotations=WRITE)
    async def export_figure(
        ref: str,
        format: Literal["svg", "png", "pdf"] = "svg",
        name: str | None = None,
        replace: bool = False,
    ) -> dict[str, Any]:
        """Export a vega or plotly figure (run:<id>/views/<name>.json or
        experiment:<name>/views/<name>.json) to reports/figures/<name>.<format>, for a deck or a
        document. A sidecar <file>.refs.json keeps its ref and trace. Put the ref in the slide's
        speaker notes or beside the figure in a document. An existing file is
        kept unless replace is set."""
        body = {"ref": ref, "format": format, "name": name, "replace": replace}
        return await post("/reports/figures", body)

    @mcp.tool(annotations=READ)
    async def check(path: str | None = None) -> list[dict[str, Any]]:
        """What in the project's Markdown, decks and Word documents is not grounded, file and
        line (slide, paragraph): a result number (0.92,
        78%, 12/40) with no ref or citation in its paragraph, list item or table; a citation
        naming no source, no page or a page with nothing pinned; a ref that does not resolve; a
        pin whose words are no longer on its page. path is a file or folder in the project; every
        .md, .pptx and .docx under experiments/ and reports/ when empty. Run it before handing
        over a write-up and fix each issue, or tell the user which you could not source."""
        return await get("/check", path=path)

    @mcp.tool(annotations=WRITE)
    async def add_view(
        name: str, view: dict[str, Any], run_id: str | None = None, experiment: str | None = None
    ) -> dict[str, Any]:
        """Draw a figure the person asked for, from data you have read or computed, and keep it:
        with run_id, in that run's Figures (views/<name>.json; an analysis or training run);
        with experiment, on its page (experiments/<experiment>/views/<name>.json, to commit).
        The same name replaces it, which is how to edit it. view is a figure as figure returns
        one: heatmap, line, scatter, table, tokens, vega (any Vega-Lite spec, data inline; its
        params animate) or plotly (traces inline: scatter3d for points in 3D, frames to play).
        Give it an about: how to read it. When its marks are items of a run (points of an
        embedding, one per record), give it items: {"run": None or the run, "folder": the item
        folder}, the ids of each plotly trace (or, for vega, items.field: the data field) being
        the items' keys; then a mark opens its item and trace follows it. Then point the
        person at it with ui_show: the part is figures/figure/<path> on the run's figures tab,
        experiment/view/<path> on the experiment's page."""
        if (run_id is None) == (experiment is None):
            raise ToolError("give run_id or experiment, one of them")
        where = (f"/runs/{quote(run_id, safe='')}" if run_id
                 else f"/experiments/{quote(experiment or '', safe='')}")  # fmt: skip
        return await send("PUT", f"{where}/views/{quote(name, safe='')}", json=view)

    @mcp.tool(annotations=WRITE)
    async def derive(run_id: str, script: str, name: str | None = None) -> dict[str, Any]:
        """Compute something new from a run's files and keep it with the run, through the job
        queue (so a script that embeds on the GPU waits its turn). script is a Python file you
        wrote in the project, experiments/<name>/derive/<what>.py, with derive(files: Path):
        files is a folder with a copy of every file the run logged. Return rows (dicts with the
        records' key, such as {"qid": 28, "label": "hedged"}) for new columns on the run's Items
        (part items/column/<name>.<field>), or a figure as add_view takes one (views/<name>.json
        on its Figures tab: plotly scatter3d for points in 3D). Waits up to ten minutes and
        returns the job; its log ends with what was added. Then ui_show the person to it."""
        options = {"run": run_id, "script": script, **({"--name": name} if name else {})}
        job = await post("/launch", {"id": "derive", "options": options})
        return await _wait(job["id"], 600)

    @mcp.tool(annotations=READ)
    async def eval_tasks(search: str | None = None) -> list[dict[str, Any]]:
        """Inspect tasks launch "eval" runs (option task): the project's @task functions
        (experiments/<name>/task.py@fn), then inspect_evals' benchmarks (inspect_evals/<name>),
        each with its title, group, what it measures and samples. search filters by any of
        them, case-insensitively."""
        found = await get("/evals")
        if search:
            word = search.lower()
            found = [t for t in found if word in " ".join(str(v) for v in t.values()).lower()]
        return found

    @mcp.tool(annotations=READ)
    async def ab_results(a: str, b: str) -> dict[str, Any]:
        """What the person's blind A/B picks of two eval runs say (Compare's Blind A/B): pairs
        picked of total, A wins, B wins, ties, B's win rate (B 1, tie 0.5, A 0) with its 95%
        interval, and each judge run of the same runs with its agreement and kappa against the
        person. Report the rate with its interval and n, never alone."""
        return await get("/ab/result", a=a, b=b)

    @mcp.tool(annotations=READ)
    async def judges() -> list[dict[str, Any]]:
        """The judges that can read two eval runs' pairs (launch "judge" with --judge <name>):
        louped's default and the project's judges/<name>.py, each with its criterion, prompt,
        model and whether it parses replies itself."""
        return await get("/judges")

    @mcp.tool(annotations=WRITE)
    async def new_judge(
        name: str,
        criterion: str,
        prompt: str | None = None,
        model: str | None = None,
        about: str | None = None,
    ) -> dict[str, Any]:
        """Write judges/<name>.py (replacing one of that name): criterion is the question for each
        pair; prompt, when the default's wording does not fit, fills {request}, {first},
        {second} and {criterion} and asks for a last line "Verdict: 1", "Verdict: 2" or
        "Verdict: tie"; model is the judge model it is meant for; about says what it is for.
        For a verdict in another form, add a verdict(reply) function to the file yourself."""
        body = {"criterion": criterion, "prompt": prompt, "model": model, "about": about}
        return await send("PUT", f"/judges/{quote(name, safe='')}", json=body)

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
    async def cohort(
        run: str,
        ids: list[str] | None = None,
        folder: str | None = None,
        field: str | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """A run's per-item records (a folder of JSONL files, one per condition) on some items:
        ids as the records' key holds them (ui_selection's items/row parts name them; None for
        every item). Each condition's value (rate and Wilson interval for a 0/1 field), and its
        paired difference from the reference with a 95% bootstrap interval, and which ids no
        file holds. Unset, folder is the first by name, field a conventional outcome name (correct,
        score, ...) else the first 0/1 field, reference a baseline-like file else the first by
        name; pass them to match what the person sees on the Items tab."""
        body = {"ids": ids, "folder": folder, "field": field, "reference": reference}
        return await post(f"/runs/{quote(run, safe='')}/cohort", body)

    @mcp.tool(annotations=READ)
    async def cohorts(experiment: str) -> list[dict[str, Any]]:
        """The cohorts saved in an experiment: name, ids, the run and folder they came from,
        and why (note)."""
        return await get(f"/experiments/{quote(experiment, safe='')}/cohorts")

    @mcp.tool(annotations=WRITE)
    async def save_cohort(
        experiment: str,
        name: str,
        ids: list[str],
        note: str,
        run: str | None = None,
        folder: str = "",
        key: str | None = None,
    ) -> dict[str, Any]:
        """Save items as a cohort (experiments/<experiment>/cohorts/<name>.json; name is
        lowercase letters, digits and -), with a note on what they have in common. A run.py
        takes it with a --cohort option that reads louped.tracking.cohort_ids(EXPERIMENT,
        name), so a run can be made on just them."""
        body = {"ids": ids, "note": note, "run": run, "folder": folder, "key": key}
        path = f"/experiments/{quote(experiment, safe='')}/cohorts/{quote(name, safe='')}"
        return await send("PUT", path, json=body)

    @mcp.tool(annotations=READ)
    async def vectors() -> list[dict[str, Any]]:
        """Saved directions: name, model, layer, method (diff-in-means, logistic-probe,
        sae-decoder), norm and the run that made each."""
        return await get("/vectors")

    @mcp.tool(annotations=READ)
    async def launchables() -> list[dict[str, Any]]:
        """What can be started: experiment scripts and notebooks, training configs, grids, data
        steps and louped's commands (new, sweep, features, circuit, grid, eval). A notebook's
        options are its parameters; its run keeps the executed copy under notebook/."""
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
        Slurm cluster or a VM, or a notebook for Colab. id and options are as for launch; target
        holds provider (sol, slurm, shell or colab), gpu, gpus, hours, cpus, partition, qos and
        constraint, the server filling in the rest (colab takes no GPU fields: the person picks
        the runtime). Saves it under out_dir and returns its path and a note: one file,
        louped-<job>.sh, when the project is a pushed git commit, else louped-<job>.tar.gz with
        job.sh inside; for colab, louped-<job>.ipynb, which needs a pushed commit. The person runs
        it there (`sbatch`, bash on a VM, Run all in Colab with an HF_TOKEN secret for gated
        models). With a remote set, its results come back with pull; else they bring back
        louped-result-<job>.tar.gz for import_result."""
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

    @mcp.tool(annotations=READ)
    async def ui_page(experiment: str | None = None) -> dict[str, Any]:
        """The app's pages as data: each region (home, run.tabs, run.overview, experiment.tabs,
        experiment.design) with its blocks and where they come from, the blocks each region can
        hold, the presets, the layout files, the part rules in force, and every kind of part by
        address with the rules it takes. With experiment, as that experiment's page and its runs'
        pages show. Change a region with set_layout, a preset with set_preset and a part with
        set_part; the change-ui skill says how to keep a page louped's own."""
        found = await get("/ui/layout", experiment=experiment)
        return {**found, **await get("/ui/catalog")}

    @mcp.tool(annotations=READ)
    async def ui_selection() -> dict[str, Any] | None:
        """What the person picked in the app with Shift+click, in the tray's order (pick 1
        first): the page, its run or experiment, and each part's address, text and data (an
        item's record under every condition, a condition's numbers, a field's value). None when
        they have picked nothing since the server started; parts is empty once they clear it.
        The tray then says you have read them."""
        picks = await get("/ui/selection")
        if picks and picks["parts"]:
            await post("/ui/selection/read", {"version": picks["version"]})
        return picks

    @mcp.tool(annotations=WRITE)
    async def set_layout(
        region: str, blocks: list[dict[str, Any]] | None, experiment: str | None = None
    ) -> dict[str, Any]:
        """Set one region's blocks, in order, in layout.json (the project's, or with experiment
        that experiment's, for its page and its runs'). A block is {"block": name} plus what its
        kind needs (key, path, index, plugin) and optionally title, about and width (full, half,
        side). blocks None removes the region from the file. The server checks it first; the app
        shows it at once. Returns the page as ui_page does."""
        body = {"region": region, "blocks": blocks, "experiment": experiment}
        return await send("PUT", "/ui/layout", json=body)

    @mcp.tool(annotations=WRITE)
    async def set_preset(preset: str | None, experiment: str | None = None) -> dict[str, Any]:
        """Start the project's (or an experiment's) pages from a preset (ui_page lists them).
        "default" uses none, even over the project's; None names none in this file, so an
        experiment follows the project's. Regions set in layout.json stay over it."""
        return await send("PUT", "/ui/preset", json={"preset": preset, "experiment": experiment})

    @mcp.tool(annotations=WRITE)
    async def set_part(
        part: str, rule: dict[str, Any] | None, experiment: str | None = None
    ) -> dict[str, Any]:
        """Change a part of the app's pages by its address (ui_selection gives it; * stands for
        any one name, as in "item/field/*/abstain"): rule is any of hidden, label, about, note
        (Markdown under it), order (among its siblings) and default (a control's value), as its
        kind takes (ui_page lists them). None removes the rule. Saved in layout.json, the
        project's or with experiment that experiment's; the app shows it at once."""
        body = {"part": part, "rule": rule, "experiment": experiment}
        return await send("PUT", "/ui/part", json=body)

    @mcp.tool(annotations=WRITE)
    async def ui_show(
        url: str | None = None,
        parts: list[str] | None = None,
        text: str | None = None,
        style: str = "highlight",
    ) -> dict[str, Any]:
        """Show the person something in the open app: open url (a path such as
        "/run/?id=m-1&tab=items&item=28"), scroll to parts by address and point at them
        (style highlight, spotlight to dim the rest, or pointer), with text (Markdown) beside the
        first until they dismiss it. Use it to answer with the evidence on screen. Returns
        whether the app showed it and which parts it could not find there."""
        body = {"url": url, "parts": parts or [], "text": text, "style": style}
        cue = await post("/ui/show", body)
        # the app picks a cue up within a second, opens its page and looks for its parts for up
        # to eight seconds
        for _ in range(SHOW_WAIT * 2):
            await asyncio.sleep(0.5)
            cue = await get(f"/ui/show/{cue['id']}")
            if cue["status"] != "pending":
                return cue
        return {**cue, "note": f"no open app showed it in {SHOW_WAIT} s; is the app open?"}

    async def _wait(job_id: str, seconds: int) -> dict[str, Any]:
        for _ in range(seconds * 2):
            found = await get(f"/launch/jobs/{job_id}")
            if found["status"] == "failed":
                raise ToolError(f"job {job_id} failed:\n{found['log']}")
            if found["status"] not in ("queued", "running"):
                return found
            await asyncio.sleep(0.5)
        return await get(f"/launch/jobs/{job_id}")

    # the project's plugins add their own tools (louped.core.plugins)
    for plugin in find_plugins():
        module = plugin.load()
        if module is not None and (add := getattr(module, "tools", None)) is not None:
            add(mcp, api)
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

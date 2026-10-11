"""The louped command."""

from __future__ import annotations

import json
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import tyro

from louped import __version__
from louped.data.cli import Command as DataCommand
from louped.train.cli import Command as TrainCommand

if TYPE_CHECKING:
    from louped.server.remote import Imported


@dataclass(frozen=True)
class Serve:
    """Start the API and, when it has been built, the UI. Models, runs and jobs are picked in the
    UI: Probe and Benchmark load a model; Launch starts experiments, training, grids and evals."""

    host: str = "127.0.0.1"
    port: int = 8000
    web_dir: Path | None = None
    """The UI's static export; by default the one in the installed package, else a checkout's
    apps/web/out (built by `just web-build`)."""
    expose: bool = False
    """Allow a host other than this machine. There is no auth: whoever reaches the port reads
    every run, log and transcript. Launching and loading a model from the UI are off when
    exposed."""
    restart: bool = False
    """Stop the louped serve this project recorded on this port (only that process), then start.
    Each serve records itself under <home>/serve/<port>.json."""


@dataclass(frozen=True)
class Init:
    """Make a research project: louped.toml, experiments/ with an example that runs on a CPU,
    AGENTS.md and the skills and MCP server for your coding agent, and .louped/ gitignored. Files
    that exist are kept."""

    path: tyro.conf.Positional[Path] = Path(".")
    """The project's folder; made if missing."""
    example: bool = True
    """Add the example experiment, does-pushback-flip-answers."""


@dataclass(frozen=True)
class View:
    """Open results you already have in the UI, read-only, without a project: a folder of Inspect
    logs, a louped home or MLflow store (mlflow.db), or any folder of files (JSONL, Markdown, JSON,
    CSV), which shows as one run."""

    path: tyro.conf.Positional[Path]
    host: str = "127.0.0.1"
    port: int = 8000
    web_dir: Path | None = None
    """The UI's static export; found as for serve."""


@dataclass(frozen=True)
class Data:
    """Training sets from logged model calls or a teacher: export, verify, review, curate, stats."""

    cmd: tyro.conf.OmitArgPrefixes[tyro.conf.OmitSubcommandPrefixes[DataCommand]]  # type: ignore[valid-type]


@dataclass(frozen=True)
class Sweep:
    """Run an Inspect task under Steer at every layer and strength; one figure of score and
    coherence cost."""

    task: str
    """An Inspect task: file.py@name, or a registered name."""
    model: str
    """A Hub id, a path, or a name under <home>/models, served through louped/."""
    vector: str
    layers: list[int]
    alphas: list[float]
    metric: str
    """scorer/metric, as the Run page shows it (refusal/mean)."""
    experiment: str = "steering-sweep"


@dataclass(frozen=True)
class Grid:
    """Run tasks under conditions over seeds, each condition against a baseline with paired
    intervals; one figure."""

    config: tyro.conf.Positional[Path]
    """YAML with model, tasks (name: file.py@task), conditions (name: model args), metric, and
    optionally seeds, baseline, held and experiment."""


@dataclass(frozen=True)
class New:
    """Start a research question: experiments/<name>/ with its README to fill in, active."""

    name: tyro.conf.Positional[str]
    """Named for the question, lowercase with dashes: does-pushback-flip-answers."""
    domain: str
    """The domain it is filed under on the Experiments page: one the project's louped.toml lists,
    else mechanisms, honesty, conditioning, agents, context, inference, specialisation or
    reproduction."""
    project: str | None = None
    """The project it is part of: one under projects/ (louped project new)."""


@dataclass(frozen=True)
class ProjectCmd:
    """Start a project that holds experiments: projects/<name>/README.md with its front matter
    and the sections to fill in. An experiment joins it with project: <name> in its README."""

    action: tyro.conf.Positional[Literal["new"]]
    name: tyro.conf.Positional[str]
    """Lowercase with dashes: sycophancy-under-pushback."""
    title: str | None = None
    """Its name for people; the folder's name by default."""
    summary: str = ""
    """One line on what it is for."""


@dataclass(frozen=True)
class Features:
    """Feature dashboards for an SAE over a dataset: density, a histogram, top examples and the
    tokens each feature promotes, on the app's Feature pages. Needs the sae extra."""

    model: str
    """A Hub id, a path, or a name under <home>/models."""
    sae: str
    """An SAELens release (gpt2-small-res-jb, gemma-scope-2b-pt-res-canonical) or a local SAE."""
    sae_id: str | None = None
    """The SAE within the release; omit for a local directory."""
    dataset: str = "NeelNanda/pile-10k"
    """A Hugging Face dataset, or a .txt (one text per line) or .jsonl file."""
    split: str = "train"
    column: str = "text"
    n: int = 256
    """Texts to read."""
    max_tokens: int = 128
    """Each text cut to this many tokens."""
    features: list[int] = field(default_factory=list)
    """Only these features; by default the top ones by peak activation."""
    top_n: int = 24
    k: int = 8
    """Top examples per feature."""
    experiment: str = "features"
    revision: str | None = None


@dataclass(frozen=True)
class Circuit:
    """An attribution graph with circuit-tracer, in its own environment through uv, on the app's
    Circuits page. Transcoders are a Hub repo matching the model."""

    model: str
    """e.g. Qwen/Qwen3-0.6B, google/gemma-2-2b."""
    transcoders: str
    """e.g. mwhanna/qwen3-0.6b-transcoders-lowl0, mwhanna/gemma-scope-transcoders."""
    prompt: str
    slug: str = "graph"
    """The graph's name on the Circuits page."""
    dtype: str = "bfloat16"
    """float32 needs about twice the GPU memory."""
    batch_size: int = 64
    """Backward passes at once; halved on its own when the GPU runs out of memory."""


@dataclass(frozen=True)
class Import:
    """Add a result from another machine to this louped: the louped-result-<id>.tar.gz an exported
    job wrote (Launch → Export), or the folder it unpacks to."""

    path: tyro.conf.Positional[Path]


@dataclass(frozen=True)
class Push:
    """Push the runs this louped made and has not pushed to the remote, as one new bundle: `remote`
    in louped.toml, or LOUPED_REMOTE. At a terminal it asks for a remote when none is set (a
    private HF bucket of your own by default) and for a Hugging Face token when an hf:// remote
    needs one."""

    remote: str | None = None
    """A remote other than the configured one: any fsspec URL, such as hf://buckets/<user>/<name>."""
    result: Path | None = None
    """An exported job's out/result.json: the bundle carries its job, host, exit code and log."""


@dataclass(frozen=True)
class Pull:
    """Add the runs in the remote's bundles this louped has not pulled. A job exported from here
    and pushed from the cluster takes its result."""

    remote: str | None = None
    """A remote other than the configured one."""


@dataclass(frozen=True)
class Gate:
    """Check an experiment's gate (gate: in its README): each requirement against the newest
    finished run of the launch it reads, PASS or FAIL. Exits 0 when all pass, else 1, so it can
    run as a chain's step on a cluster."""

    experiment: tyro.conf.Positional[str]
    pull: bool = False
    """Pull the remote's new runs first: the gate step on a cluster, which reads the runs the
    steps before it pushed."""


@dataclass(frozen=True)
class Submit:
    """Send a launch to a cluster named in louped.toml ([clusters.<name>]) over ssh: export it,
    copy it there, start it (sbatch, or bash on a VM) and record it as a job. louped serve
    follows it and brings its result here."""

    what: tyro.conf.Positional[str]
    """A launchable id, such as script:<name>/train.py, or gate (with --experiment); with
    --chain, an experiment."""
    on: str
    """The cluster."""
    after: str | None = None
    """A louped job on that cluster this one waits for and needs to succeed (Slurm only)."""
    chain: bool = False
    """Submit the experiment's chain: steps in order, each after the one before."""
    experiment: str | None = None
    """For gate: the experiment whose gate the step checks."""
    gpu: str | None = None
    """The GPU type: on Sol a100 (the default), a30, h100, mi200, 1g.20gb or 2g.20gb; on Slurm a
    gres type, any when empty."""
    gpus: int = 1
    hours: int = 4


@dataclass(frozen=True)
class Cluster:
    """A cluster named in louped.toml. token copies this machine's Hugging Face token to the
    cluster's ~/.cache/huggingface/token over ssh (mode 600), where gated models read it; it
    goes on ssh's stdin, never into a command line, job.sh or a log."""

    action: tyro.conf.Positional[Literal["token"]]
    name: tyro.conf.Positional[str]


@dataclass(frozen=True)
class Hub:
    """get puts a model or dataset from the Hugging Face Hub in this machine's cache
    (huggingface_hub's snapshot_download), where loading it finds it. A gated one needs a token
    with access: hf auth login, or the app's Hub page."""

    action: tyro.conf.Positional[Literal["get"]]
    repo: tyro.conf.Positional[str]
    """The repository id, such as Qwen/Qwen2.5-0.5B-Instruct."""
    dataset: bool = False
    """It is a dataset, not a model."""


@dataclass(frozen=True)
class Publish:
    """Write this project's dashboard as static, read-only files to put on any static host at a
    domain's root: an HF static Space, Vercel, or a GitHub Pages user site."""

    out: tyro.conf.Positional[Path]
    """An empty or new folder."""
    web_dir: Path | None = None
    """The UI's static export; found as for serve."""


@dataclass(frozen=True)
class Bench:
    """What serving a model costs on this machine, per weight format: throughput and latency as
    requests arrive together, and prefill time and memory as the prompt grows. One run with its
    figures. int8 and int4 need CUDA and the train extra."""

    model: str
    """A Hub id, a path, or a name under <home>/models."""
    quants: list[Literal["none", "int8", "int4"]] = field(default_factory=lambda: ["none"])
    """Weight formats to compare: none (as saved), int8, int4 (NF4)."""
    batches: list[int] = field(default_factory=lambda: [1, 4, 16])
    """Requests generated at once."""
    contexts: list[int] = field(default_factory=lambda: [512, 2048, 8192])
    """Prompt lengths in tokens; ones over the model's limit are skipped."""
    new_tokens: int = 64
    """Tokens each request generates."""
    repeats: int = 3
    experiment: str = "efficiency-bench"
    draft: str | None = None
    """A small model with the same tokenizer, to draft for speculative decoding (Qwen/Qwen2.5-0.5B
    for a larger Qwen2.5); prompt lookup is measured either way."""
    profile: bool = True
    """Profile one request: the operators it spent most time in and a trace for Perfetto."""
    remote_code: bool = False
    """Run the modeling code the Hub repository ships (trust_remote_code); pin its revision."""


@dataclass(frozen=True)
class EndpointBench:
    """What a served model costs where it runs: time to first token, latency and throughput as
    requests arrive together, against OpenAI-compatible servers (llama-server, vLLM, Ollama, your
    own engine). One run, every request recorded so two servers line up on the Items tab."""

    urls: tyro.conf.Positional[list[str]]
    """Base URLs ending in /v1, one per server to compare: http://127.0.0.1:8080/v1."""
    model: str = "default"
    """The model name the servers expect in a request (llama-server accepts any)."""
    levels: list[int] = field(default_factory=lambda: [1, 2, 4, 8])
    """Requests in flight at once."""
    rounds: int = 3
    """Times each level is sent."""
    prompt_words: int = 200
    max_tokens: int = 128
    experiment: str = "efficiency-bench"


@dataclass(frozen=True)
class Judge:
    """Two eval runs judged sample by sample by a local model, each pair in both orders: B's win
    rate over A as an eval run of its own."""

    a: tyro.conf.Positional[str]
    """The baseline run's id."""
    b: tyro.conf.Positional[str]
    """The changed run's id."""
    judge: str = "default"
    """Which judge reads the pairs: default, or one of the project's judges/<name>.py."""
    model: str | None = None
    """The judge model, else the judge's own (MODEL): louped/ or hf/ with a Hub id runs locally;
    any Inspect model works."""
    criterion: str | None = None
    """The question for each pair, else the judge's own (CRITERION)."""
    limit: int | None = None
    """Pairs to judge; all when empty."""
    max_tokens: int = 512


@dataclass(frozen=True)
class Export:
    """Export a vega or plotly figure to reports/figures/, with a sidecar holding its ref and
    trace."""

    ref: tyro.conf.Positional[str]
    """run:<id>/views/<name>.json or experiment:<name>/views/<name>.json."""
    format: Literal["svg", "png", "pdf"] = "svg"
    name: str | None = None
    """The file's name; from the ref when empty."""
    replace: bool = False
    """Write over a file of the same name."""


@dataclass(frozen=True)
class Check:
    """Check the project's Markdown is grounded: each result number (0.92, 78%, 12/40) beside a
    ref or citation, each citation on a pinned page, each ref resolving, each pin still on its
    page. Exits 1 when anything is not."""

    paths: tyro.conf.Positional[tuple[Path, ...]] = ()
    """Markdown files or folders; every .md under experiments/ and reports/ when none."""
    json: bool = False
    """Print the issues as JSON."""


@dataclass(frozen=True)
class Render:
    """Print a Markdown file with each live ref's metric ({{run:<id> <metric>}}) replaced by its
    value. Figures stay as written. Exits 1, naming them, when any live ref does not resolve."""

    file: tyro.conf.Positional[Path]


@dataclass(frozen=True)
class Derive:
    """A script over a run's files, kept with the run: its derive(files) returns rows (new
    columns on the run's Items, as derived/<name>.jsonl) or a figure (views/<name>.json)."""

    run: tyro.conf.Positional[str]
    """The run's id (an analysis or training run)."""
    script: tyro.conf.Positional[Path]
    """A Python file with derive(files: Path), such as experiments/<name>/derive/<what>.py."""
    name: str | None = None
    """What it is logged as; the script's name when empty."""


@dataclass(frozen=True)
class Notebook:
    """Run a notebook in experiments/<name>/ with papermill, inside a run in that experiment; the
    run keeps the executed copy with every output."""

    notebook: tyro.conf.Positional[Path]
    """The .ipynb file, such as experiments/<name>/explore.ipynb."""
    param: tuple[str, ...] = ()
    """name=value for a variable of the cell tagged "parameters"; repeat for more."""


@dataclass(frozen=True)
class SourceAdd:
    """Keep a paper, doc, deck or notebook in sources/: a file, or an https URL (an arXiv page,
    a shared Google Doc or Slides deck, a notebook on GitHub, a direct file link)."""

    location: tyro.conf.Positional[str]
    key: str | None = None
    """What citations name it by; from its title when empty."""
    title: str | None = None


@dataclass(frozen=True)
class SourceSearch:
    """The pages of sources/ holding every word of the query, best first."""

    query: tyro.conf.Positional[str]
    limit: int = 10


@dataclass(frozen=True)
class SourceList:
    """Every source in sources/index.json."""


SourceCommand = (
    Annotated[SourceAdd, tyro.conf.subcommand("add")]
    | Annotated[SourceSearch, tyro.conf.subcommand("search")]
    | Annotated[SourceList, tyro.conf.subcommand("list")]
)


@dataclass(frozen=True)
class Sources:
    """The project's sources/: papers, docs, slides and notebooks, searched and cited."""

    cmd: tyro.conf.OmitArgPrefixes[tyro.conf.OmitSubcommandPrefixes[SourceCommand]]  # type: ignore[valid-type]


@dataclass(frozen=True)
class Mcp:
    """An MCP server on stdio for coding agents, over a running louped serve: read experiments,
    runs, figures and compares; launch, follow and cancel jobs."""

    url: str = "http://127.0.0.1:8000"
    """The louped serve to drive."""


@dataclass(frozen=True)
class Picks:
    """What the person Shift+clicked in the app, as text for an agent, numbered as the tray
    numbers them. With --hook, a Claude Code UserPromptSubmit hook: it adds the picks to the
    message when they are new to the agent or the message says @sel (or @sel 2, @sel 1,3)."""

    hook: bool = False
    """Read the hook's JSON on stdin and print the hook's output."""
    url: str = "http://127.0.0.1:8000"
    """The louped serve the app runs on."""


@dataclass(frozen=True)
class Examples:
    """Example runs for every page, from a tiny model trained here on the CPU: a vector, an
    analysis with every figure, a grid of evals, a fine-tune, a benchmark and a circuit. Their
    numbers check the pipeline, not a claim. Needs the train, rl and sae extras."""


@dataclass(frozen=True)
class Version:
    """Print the installed version."""


Command = (
    Annotated[Serve, tyro.conf.subcommand("serve")]
    | Annotated[Data, tyro.conf.subcommand("data")]
    | Annotated[TrainCommand, tyro.conf.subcommand("train")]
    | Annotated[Sweep, tyro.conf.subcommand("sweep")]
    | Annotated[Grid, tyro.conf.subcommand("grid")]
    | Annotated[Init, tyro.conf.subcommand("init")]
    | Annotated[New, tyro.conf.subcommand("new")]
    | Annotated[ProjectCmd, tyro.conf.subcommand("project")]
    | Annotated[View, tyro.conf.subcommand("view")]
    | Annotated[Features, tyro.conf.subcommand("features")]
    | Annotated[Circuit, tyro.conf.subcommand("circuit")]
    | Annotated[Import, tyro.conf.subcommand("import")]
    | Annotated[Push, tyro.conf.subcommand("push")]
    | Annotated[Pull, tyro.conf.subcommand("pull")]
    | Annotated[Gate, tyro.conf.subcommand("gate")]
    | Annotated[Submit, tyro.conf.subcommand("submit")]
    | Annotated[Cluster, tyro.conf.subcommand("cluster")]
    | Annotated[Hub, tyro.conf.subcommand("hub")]
    | Annotated[Publish, tyro.conf.subcommand("publish")]
    | Annotated[Bench, tyro.conf.subcommand("bench")]
    | Annotated[EndpointBench, tyro.conf.subcommand("endpoint-bench")]
    | Annotated[Judge, tyro.conf.subcommand("judge")]
    | Annotated[Derive, tyro.conf.subcommand("derive")]
    | Annotated[Notebook, tyro.conf.subcommand("notebook")]
    | Annotated[Check, tyro.conf.subcommand("check")]
    | Annotated[Render, tyro.conf.subcommand("render")]
    | Annotated[Export, tyro.conf.subcommand("export")]
    | Annotated[Sources, tyro.conf.subcommand("source")]
    | Annotated[Mcp, tyro.conf.subcommand("mcp")]
    | Annotated[Picks, tyro.conf.subcommand("picks")]
    | Annotated[Examples, tyro.conf.subcommand("examples")]
    | Annotated[Version, tyro.conf.subcommand("version")]
)

#: louped's own commands; a plugin of the same name does not replace one.
COMMANDS = {
    "serve",
    "data",
    "train",
    "sweep",
    "grid",
    "init",
    "new",
    "project",
    "view",
    "features",
    "circuit",
    "import",
    "push",
    "pull",
    "gate",
    "submit",
    "cluster",
    "hub",
    "publish",
    "bench",
    "endpoint-bench",
    "judge",
    "derive",
    "notebook",
    "check",
    "render",
    "export",
    "source",
    "mcp",
    "examples",
    "version",
}


def serve(cmd: Serve) -> None:
    import uvicorn

    from louped.server import create_app, serving
    from louped.server.app import LOOPBACK, find_ui

    hosts = None
    if cmd.host not in LOOPBACK:
        if not cmd.expose:
            raise SystemExit(f"--host {cmd.host} serves every log without auth; add --expose")
        hosts = ["*"] if cmd.host in ("0.0.0.0", "::") else [*LOOPBACK, cmd.host]
    app = create_app(find_ui(cmd.web_dir), hosts, launching=hosts is None)
    serving.claim(cmd.host, cmd.port, restart=cmd.restart)
    serving.record(cmd.host, cmd.port)
    # uvicorn shuts down on SIGTERM, then raises it again under the handler it found: this one
    # exits through the finally below, where the default would end the process before it
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + signal.SIGTERM))
    try:
        uvicorn.run(app, host=cmd.host, port=cmd.port)
    finally:
        serving.forget(cmd.port)


def view(cmd: View) -> None:
    import uvicorn

    from louped.server import create_app
    from louped.server.app import LOOPBACK, find_ui
    from louped.server.view import prepare

    if cmd.host not in LOOPBACK:
        raise SystemExit("louped view serves this machine only; use louped serve --expose to share")
    try:
        print(prepare(cmd.path))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    uvicorn.run(create_app(find_ui(cmd.web_dir), None, launching=False), host=cmd.host,
                port=cmd.port)  # fmt: skip


def _imported(done: Imported) -> str:
    again = f", {len(done.skipped)} already here" if done.skipped else ""
    return f"{len(done.runs)} runs from {done.host} (exit {done.exit_code}){again}"


def _connect(given: str | None) -> None:
    """At a terminal, ask for what push and pull lack: a remote for the project, and a Hugging Face
    token for an hf:// one. Elsewhere (a cluster job) they fail with what to set instead."""
    import sys
    from getpass import getpass

    from louped import sync

    if not sys.stdin.isatty():
        return
    url = given or sync.configured()
    if url is None:
        url = input("Remote (Enter for a private Hugging Face bucket of your own): ").strip()
    if (not url or sync.bucket(url)) and not sync.has_token():
        print("A Hugging Face token with write access: https://huggingface.co/settings/tokens")
        print(f"Signed in as {sync.save_token(getpass('Token: ').strip())}")
    if not url:
        url = sync.suggested()
        assert url is not None  # a token was just saved
    if given is None and sync.configured() is None:
        sync.set_remote(url)
        print(f"remote = {url} (louped.toml)")


def _gate(cmd: Gate) -> None:
    from louped.core import experiments_dir
    from louped.stores import gates

    if not (experiments_dir() / cmd.experiment / "README.md").is_file():
        raise SystemExit(f"no experiment {cmd.experiment} in {experiments_dir()}")
    if cmd.pull:
        from louped.sync import pull

        try:
            print(f"pulled {len(pull())} new bundles")
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    gate = gates.status(cmd.experiment)
    if gate is None:
        raise SystemExit(f"experiments/{cmd.experiment}/README.md declares no gate")
    if gate.error:
        raise SystemExit(gate.error)
    print(f"{cmd.experiment}'s gate reads {gate.launch}: "
          f"{f'run {gate.run}' if gate.run else 'no finished run yet'}")  # fmt: skip
    width = max(len(c.requirement) for c in gate.checks)
    for c in gate.checks:
        value = "missing" if c.actual is None else f"{c.actual:g}"
        print(f"  {'PASS' if c.passed else 'FAIL'}  {c.requirement:<{width}}  {value:>10}")
    guarded = ", ".join(gate.guards) or "nothing"
    print(f"PASS: {guarded} may run." if gate.passed else f"FAIL: {guarded} waits.")
    raise SystemExit(0 if gate.passed else 1)


def _submit(cmd: Submit) -> None:
    from fastapi import HTTPException

    from louped import clusters
    from louped.server.launch import Jobs, catalogue
    from louped.server.remote import Target
    from louped.server.submit import SubmitFailed, SubmitRequest, chain, submit
    from louped.stores.gates import GateClosed

    titles = {x.id: x.title for x in catalogue()}
    try:
        provider = clusters.get(cmd.on).provider
        target = Target(provider=provider, gpus=cmd.gpus, hours=cmd.hours)
        if cmd.gpu or provider != "sol":  # Sol's default is a100; elsewhere any GPU
            target = Target(provider=provider, gpus=cmd.gpus, hours=cmd.hours, gpu=cmd.gpu)
        jobs = Jobs(work=False)
        if cmd.chain:
            if cmd.after:
                raise ValueError("--chain starts a chain of its own; it takes no --after")
            done = chain(cmd.what, cmd.on, jobs, titles, target)
        elif cmd.what not in titles:
            raise ValueError(f"{cmd.what!r} is not something louped can launch: Launch lists "
                             "the ids, such as script:<name>/train.py")  # fmt: skip
        elif (cmd.what == "gate") != (cmd.experiment is not None):
            raise ValueError(
                "a gate step names its experiment, and only it: gate --experiment <name>"
            )
        else:
            options: dict[str, str | bool | list[str]] = (
                {"experiment": cmd.experiment} if cmd.experiment else {}
            )
            req = SubmitRequest(id=cmd.what, cluster=cmd.on, after=cmd.after, target=target,
                                options=options)  # fmt: skip
            done = [submit(req, jobs, titles[cmd.what])]
    except HTTPException as exc:
        raise SystemExit(str(exc.detail)) from exc
    except (ValueError, GateClosed, SubmitFailed) as exc:
        raise SystemExit(str(exc)) from exc
    for job in done:
        after = f", after {job.after}" if job.after else ""
        print(f"{job.id}  {job.title}: {cmd.on} job {job.scheduler_id}{after}")
    print("louped serve follows it and brings its result here (louped pull, with a remote).")


def _cluster(cmd: Cluster) -> None:
    from louped import clusters

    try:
        where = clusters.send_token(clusters.get(cmd.name))
    except (ValueError, clusters.SshError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Hugging Face token copied to {where} (only you can read it)")


def _plugin_command() -> bool:
    """Run `louped <name> ...` with the project plugin of that name's main, when no command of
    louped's own has the name; whether one ran."""
    import sys

    if len(sys.argv) < 2 or sys.argv[1].startswith("-") or sys.argv[1] in COMMANDS:
        return False
    from louped.core.plugins import find_plugins

    plugin = next((p for p in find_plugins() if p.name == sys.argv[1]), None)
    module = plugin.load() if plugin is not None else None
    run = getattr(module, "main", None)
    if run is None:
        return False
    run(sys.argv[2:])
    return True


def _picks(cmd: Picks) -> None:
    import httpx

    from louped.picks import current, describe, for_prompt, hook_output, mark_read

    with httpx.Client(base_url=f"{cmd.url.rstrip('/')}/api", timeout=5) as api:
        if cmd.hook:
            prompt = json.load(sys.stdin).get("prompt", "")
            if out := hook_output(for_prompt(api, prompt)):
                print(out)
            return
        try:
            picks = current(api)
        except httpx.HTTPError as e:
            raise SystemExit(f"louped picks: no louped serve at {cmd.url}: {e}") from e
        if not picks or not picks["parts"]:
            print("Nothing is picked.")
            return
        mark_read(api, picks)
        print(describe(picks["parts"], list(range(1, len(picks["parts"]) + 1))))


def main() -> None:
    if _plugin_command():
        return
    match cmd := tyro.cli(Command):
        case Serve() as cmd:
            serve(cmd)
        case Data(cmd=sub):
            from louped.data.cli import run

            run(sub)
        case TrainCommand():
            from louped.train.cli import run as run_train

            run_train(cmd)
        case Sweep() as cmd:
            from louped.sweep import sweep

            print(sweep(cmd.task, cmd.model, cmd.vector, cmd.layers, cmd.alphas, cmd.metric,
                        cmd.experiment))  # fmt: skip
        case Grid() as cmd:
            import inspect

            import yaml

            from louped.grid import grid

            spec = yaml.safe_load(cmd.config.read_text(encoding="utf-8"))
            if unknown := set(spec) - set(inspect.signature(grid).parameters):
                raise SystemExit(f"{cmd.config}: unknown keys {sorted(unknown)}")
            print(grid(**spec))
        case Init() as cmd:
            from louped.init import init

            try:
                print(init(cmd.path, cmd.example))
            except FileExistsError as exc:
                raise SystemExit(str(exc)) from exc
        case View() as cmd:
            view(cmd)
        case New() as cmd:
            from louped.stores.experiments import BadExperiment, scaffold

            try:
                print(f"created {scaffold(cmd.name, cmd.domain, cmd.project)}")
            except BadExperiment as exc:
                raise SystemExit(str(exc)) from exc
        case ProjectCmd() as cmd:
            from louped.stores.projects import BadProject, create
            from louped.stores.types import ProjectMeta

            try:
                meta = ProjectMeta(title=cmd.title or "", summary=cmd.summary)
                print(f"created {create(cmd.name, meta) / 'README.md'}")
            except (BadProject, ValueError) as exc:
                raise SystemExit(str(exc)) from exc
        case Features() as cmd:
            from louped.features import features

            print(features(cmd.model, cmd.sae, cmd.sae_id, cmd.dataset, cmd.split, cmd.column,
                           cmd.n, cmd.max_tokens, list(cmd.features) or None, cmd.top_n, cmd.k,
                           cmd.experiment, cmd.revision))  # fmt: skip
        case Circuit() as cmd:
            from louped.circuits import circuit

            circuit(cmd.model, cmd.transcoders, cmd.prompt, cmd.slug, cmd.dtype, cmd.batch_size)
        case Import() as cmd:
            from louped.server.launch import Jobs
            from louped.server.remote import import_result

            try:
                done = import_result(cmd.path, Jobs(work=False))
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            print(_imported(done))
        case Push() as cmd:
            from louped.sync import push

            try:
                _connect(cmd.remote)
                pushed = push(cmd.remote, cmd.result)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            print(f"{len(pushed.runs)} runs to {pushed.remote}/{pushed.bundle}" if pushed.bundle
                  else "nothing new to push")  # fmt: skip
        case Pull() as cmd:
            from louped.server.launch import Jobs
            from louped.server.remote import pull_results

            try:
                _connect(cmd.remote)
                pulled = pull_results(Jobs(work=False), cmd.remote)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            for done in pulled:
                print(_imported(done))
            if not pulled:
                print("nothing new to pull")
        case Gate() as cmd:
            _gate(cmd)
        case Submit() as cmd:
            _submit(cmd)
        case Cluster() as cmd:
            _cluster(cmd)
        case Hub() as cmd:
            from huggingface_hub import snapshot_download
            from huggingface_hub.errors import HfHubHTTPError

            try:
                print(snapshot_download(cmd.repo, repo_type="dataset" if cmd.dataset else None))
            except HfHubHTTPError as exc:
                raise SystemExit(str(exc)) from exc
        case Publish() as cmd:
            from louped.server.app import find_ui
            from louped.server.publish import describe, publish

            web = find_ui(cmd.web_dir)
            if web is None:
                raise SystemExit("louped publish needs the built UI: pass --web-dir")
            try:
                print(describe(publish(cmd.out, web)))
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
        case Bench() as cmd:
            from louped.bench import bench
            from louped.models.load import Quant

            quants: list[Quant | None] = [None if q == "none" else q for q in cmd.quants]
            print(bench(cmd.model, quants, tuple(cmd.batches), tuple(cmd.contexts),
                        cmd.new_tokens, cmd.repeats, cmd.experiment, cmd.draft,
                        cmd.profile, cmd.remote_code))  # fmt: skip
        case EndpointBench() as cmd:
            from louped.endpoint_bench import endpoint_bench

            print(endpoint_bench(cmd.urls, cmd.model, tuple(cmd.levels), cmd.rounds,
                                 cmd.prompt_words, cmd.max_tokens, cmd.experiment))  # fmt: skip
        case Judge() as cmd:
            from louped.judge import judge

            try:
                print(judge(cmd.a, cmd.b, cmd.model, cmd.criterion, cmd.limit, cmd.max_tokens,
                            cmd.judge))  # fmt: skip
            except (ValueError, FileNotFoundError) as exc:
                raise SystemExit(str(exc)) from exc
        case Export() as cmd:
            from louped.reports import export_figure
            from louped.stores.runs import NotFound

            try:
                print(
                    export_figure(cmd.ref, cmd.format, cmd.name, cmd.replace).model_dump_json(
                        indent=2
                    )
                )
            except (ValueError, RuntimeError, NotFound, FileExistsError) as exc:
                raise SystemExit(str(exc)) from exc
        case Check() as cmd:
            import json

            from louped.check import check

            try:
                issues = check(list(cmd.paths) or None)
            except (ValueError, FileNotFoundError) as exc:
                raise SystemExit(str(exc)) from exc
            if cmd.json:
                print(json.dumps([i.model_dump() for i in issues], indent=2))
            else:
                for i in issues:
                    print(f"{i.where()}: {i.message}")
                print(f"{len(issues)} issue{'' if len(issues) == 1 else 's'}")
            raise SystemExit(1 if issues else 0)
        case Render() as cmd:
            from louped.reports import render

            try:
                text, broken = render(cmd.file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                raise SystemExit(f"cannot read {cmd.file}: {exc}") from exc
            print(text, end="")
            for live in broken:
                print(f"{{{{{live.text}}}}} does not resolve: {live.error}", file=sys.stderr)
            raise SystemExit(1 if broken else 0)
        case Derive() as cmd:
            import json

            from louped.derive import derive

            try:
                print(json.dumps({"run": cmd.run, "added": derive(cmd.run, cmd.script, cmd.name)}))
            except (ValueError, FileNotFoundError) as exc:
                raise SystemExit(str(exc)) from exc
        case Notebook() as cmd:
            from papermill.exceptions import PapermillExecutionError

            from louped.notebooks import run_notebook

            given: dict[str, str] = {}
            for pair in cmd.param:
                name, eq, value = pair.partition("=")
                if not eq:
                    raise SystemExit(f"--param takes name=value, not {pair!r}")
                given[name] = value
            try:
                print(run_notebook(cmd.notebook, given))
            except (ValueError, PapermillExecutionError) as exc:
                raise SystemExit(str(exc)) from exc
        case Sources(cmd=sub):
            from louped import sources

            try:
                match sub:
                    case SourceAdd():
                        print(sources.add_source(sub.location, sub.key, sub.title)
                              .model_dump_json(indent=2))  # fmt: skip
                    case SourceSearch():
                        for hit in sources.search(sub.query, sub.limit):
                            print(f"{hit.key} p{hit.page}  {hit.snippet}")
                    case SourceList():
                        for s in sources.list_sources():
                            print(f"{s.key}  {s.kind}  {s.pages}p  {s.title}")
            except (ValueError, FileNotFoundError, KeyError) as exc:
                raise SystemExit(str(exc)) from exc
        case Mcp() as cmd:
            from louped.agent import server

            server(cmd.url).run("stdio")
        case Picks() as cmd:
            _picks(cmd)
        case Examples():
            from louped.examples import examples

            examples()
        case Version():
            print(__version__)

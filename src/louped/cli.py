"""The louped command."""

from __future__ import annotations

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
    UI: the Playground loads a model, Launch starts experiments, training, grids and evals."""

    host: str = "127.0.0.1"
    port: int = 8000
    web_dir: Path | None = None
    """The UI's static export; by default the one in the installed package, else a checkout's
    apps/web/out (built by `just web-build`)."""
    expose: bool = False
    """Allow a host other than this machine. There is no auth: whoever reaches the port reads
    every run, log and transcript. Launching and loading a model from the UI are off when
    exposed."""


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
    coherence cost. Needs the evals, interp and tracking extras."""

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
    intervals; one figure. Needs the evals and tracking extras, and interp for louped/ models."""

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
    job wrote (Launch → Export), or the folder it unpacks to. Needs the server extra."""

    path: tyro.conf.Positional[Path]


@dataclass(frozen=True)
class Push:
    """Push the runs this louped made and has not pushed to the remote, as one new bundle: `remote`
    in louped.toml, or LOUPED_REMOTE. At a terminal it asks for a remote when none is set (a
    private HF bucket of your own by default) and for a Hugging Face token when an hf:// remote
    needs one. Needs the sync extra."""

    remote: str | None = None
    """A remote other than the configured one: any fsspec URL, such as hf://buckets/<user>/<name>."""
    result: Path | None = None
    """An exported job's out/result.json: the bundle carries its job, host, exit code and log."""


@dataclass(frozen=True)
class Pull:
    """Add the runs in the remote's bundles this louped has not pulled. A job exported from here
    and pushed from the cluster takes its result. Needs the sync extra."""

    remote: str | None = None
    """A remote other than the configured one."""


@dataclass(frozen=True)
class Publish:
    """Write this project's dashboard as static, read-only files to put on any static host at a
    domain's root: an HF static Space, Vercel, or a GitHub Pages user site. Needs the server
    extra."""

    out: tyro.conf.Positional[Path]
    """An empty or new folder."""
    web_dir: Path | None = None
    """The UI's static export; found as for serve."""


@dataclass(frozen=True)
class Bench:
    """What serving a model costs on this machine, per weight format: throughput and latency as
    requests arrive together, and prefill time and memory as the prompt grows. One run with its
    figures. Needs the interp and tracking extras; int8 and int4 need CUDA and the train extra."""

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
    own engine). One run, every request recorded so two servers line up on the Items tab. Needs
    the tracking and agent extras."""

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
    rate over A as an eval run of its own. Needs the evals extra, and interp for louped/ models."""

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
    runs, figures and compares; launch, follow and cancel jobs. Needs the agent extra."""

    url: str = "http://127.0.0.1:8000"
    """The louped serve to drive."""


@dataclass(frozen=True)
class Examples:
    """Example runs for every page, from a tiny model trained here on the CPU: a vector, an
    analysis with every figure, a grid of evals, a fine-tune, a benchmark and a circuit. Their
    numbers check the pipeline, not a claim. Needs every extra."""


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
    | Annotated[View, tyro.conf.subcommand("view")]
    | Annotated[Features, tyro.conf.subcommand("features")]
    | Annotated[Circuit, tyro.conf.subcommand("circuit")]
    | Annotated[Import, tyro.conf.subcommand("import")]
    | Annotated[Push, tyro.conf.subcommand("push")]
    | Annotated[Pull, tyro.conf.subcommand("pull")]
    | Annotated[Publish, tyro.conf.subcommand("publish")]
    | Annotated[Bench, tyro.conf.subcommand("bench")]
    | Annotated[EndpointBench, tyro.conf.subcommand("endpoint-bench")]
    | Annotated[Judge, tyro.conf.subcommand("judge")]
    | Annotated[Derive, tyro.conf.subcommand("derive")]
    | Annotated[Check, tyro.conf.subcommand("check")]
    | Annotated[Export, tyro.conf.subcommand("export")]
    | Annotated[Sources, tyro.conf.subcommand("source")]
    | Annotated[Mcp, tyro.conf.subcommand("mcp")]
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
    "view",
    "features",
    "circuit",
    "import",
    "push",
    "pull",
    "publish",
    "bench",
    "endpoint-bench",
    "judge",
    "derive",
    "check",
    "export",
    "source",
    "mcp",
    "examples",
    "version",
}


def serve(cmd: Serve) -> None:
    try:
        import uvicorn

        from louped.server import create_app
    except ImportError as exc:
        raise SystemExit(
            "louped serve needs the server extra: pip install 'louped[server]'"
        ) from exc
    from louped.server.app import LOOPBACK, find_ui

    hosts = None
    if cmd.host not in LOOPBACK:
        if not cmd.expose:
            raise SystemExit(f"--host {cmd.host} serves every log without auth; add --expose")
        hosts = ["*"] if cmd.host in ("0.0.0.0", "::") else [*LOOPBACK, cmd.host]
    uvicorn.run(
        create_app(find_ui(cmd.web_dir), hosts, launching=hosts is None),
        host=cmd.host,
        port=cmd.port,
    )


def view(cmd: View) -> None:
    try:
        import uvicorn

        from louped.server import create_app
        from louped.server.app import LOOPBACK, find_ui
        from louped.server.view import prepare
    except ImportError as exc:
        raise SystemExit(
            "louped view needs the server and tracking extras: "
            "pip install 'louped[server,tracking]'"
        ) from exc
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
                print(f"created {scaffold(cmd.name, cmd.domain)}")
            except BadExperiment as exc:
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
            try:
                from louped.endpoint_bench import endpoint_bench
            except ModuleNotFoundError as exc:
                raise SystemExit(
                    f"louped endpoint-bench needs the tracking and agent extras ({exc.name} is "
                    "missing): pip install 'louped[tracking,agent]'"
                ) from exc
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
                print(export_figure(cmd.ref, cmd.format, cmd.name).model_dump_json(indent=2))
            except (ValueError, RuntimeError, NotFound) as exc:
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
        case Derive() as cmd:
            import json

            from louped.derive import derive

            try:
                print(json.dumps({"run": cmd.run, "added": derive(cmd.run, cmd.script, cmd.name)}))
            except (ValueError, FileNotFoundError) as exc:
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
            try:
                from louped.agent import server
            except ModuleNotFoundError as exc:
                if exc.name not in ("mcp", "mcp_types", "httpx"):
                    raise
                raise SystemExit(
                    "louped mcp needs the agent extra: pip install 'louped[agent]'"
                ) from exc
            server(cmd.url).run("stdio")
        case Examples():
            from louped.examples import examples

            examples()
        case Version():
            print(__version__)

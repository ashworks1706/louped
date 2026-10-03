"""The loupe command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

import tyro

from loupe import __version__
from loupe.data.cli import Command as DataCommand
from loupe.stores.types import Domain
from loupe.train.cli import Command as TrainCommand


@dataclass(frozen=True)
class Serve:
    """Start the API and, when it has been built, the UI. Models, runs and jobs are picked in the
    UI: the Playground loads a model, Launch starts experiments, training, grids and evals."""

    host: str = "127.0.0.1"
    port: int = 8000
    web_dir: Path = Path("apps/web/out")
    """The UI's static export; built by `just web-build`."""
    expose: bool = False
    """Allow a host other than this machine. There is no auth: whoever reaches the port reads
    every run, log and transcript. Launching and loading a model from the UI are off when
    exposed."""


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
    """A Hub id, a path, or a name under <home>/models, served through loupe/."""
    vector: str
    layers: list[int]
    alphas: list[float]
    metric: str
    """scorer/metric, as the Run page shows it (refusal/mean)."""
    experiment: str = "steering-sweep"


@dataclass(frozen=True)
class Grid:
    """Run tasks under conditions over seeds, each condition against a baseline with paired
    intervals; one figure. Needs the evals and tracking extras, and interp for loupe/ models."""

    config: tyro.conf.Positional[Path]
    """YAML with model, tasks (name: file.py@task), conditions (name: model args), metric, and
    optionally seeds, baseline, held and experiment."""


@dataclass(frozen=True)
class New:
    """Start a research question: experiments/<name>/ with its README to fill in, active."""

    name: tyro.conf.Positional[str]
    """Named for the question, lowercase with dashes: sycophancy-pushback."""
    domain: Domain
    """The domain it is filed under on the Experiments page."""


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
    """Add a result from another machine to this loupe: the loupe-result-<id>.tar.gz an exported
    job wrote (Launch → Export), or the folder it unpacks to. Needs the server extra."""

    path: tyro.conf.Positional[Path]


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


@dataclass(frozen=True)
class Judge:
    """Two eval runs judged sample by sample by a local model, each pair in both orders: B's win
    rate over A as an eval run of its own. Needs the evals extra, and interp for loupe/ models."""

    a: tyro.conf.Positional[str]
    """The baseline run's id."""
    b: tyro.conf.Positional[str]
    """The changed run's id."""
    model: str = "loupe/Qwen/Qwen2.5-1.5B-Instruct"
    """The judge: loupe/ or hf/ with a Hub id runs locally; any Inspect model works."""
    criterion: str = "Which answer is more correct and more helpful?"
    """The question the judge answers for each pair."""
    limit: int | None = None
    """Pairs to judge; all when empty."""
    max_tokens: int = 512


@dataclass(frozen=True)
class Mcp:
    """An MCP server on stdio for coding agents, over a running loupe serve: read experiments,
    runs, figures and compares; launch, follow and cancel jobs. Needs the agent extra."""

    url: str = "http://127.0.0.1:8000"
    """The loupe serve to drive."""


@dataclass(frozen=True)
class Version:
    """Print the installed version."""


Command = (
    Annotated[Serve, tyro.conf.subcommand("serve")]
    | Annotated[Data, tyro.conf.subcommand("data")]
    | Annotated[TrainCommand, tyro.conf.subcommand("train")]
    | Annotated[Sweep, tyro.conf.subcommand("sweep")]
    | Annotated[Grid, tyro.conf.subcommand("grid")]
    | Annotated[New, tyro.conf.subcommand("new")]
    | Annotated[Features, tyro.conf.subcommand("features")]
    | Annotated[Circuit, tyro.conf.subcommand("circuit")]
    | Annotated[Import, tyro.conf.subcommand("import")]
    | Annotated[Bench, tyro.conf.subcommand("bench")]
    | Annotated[Judge, tyro.conf.subcommand("judge")]
    | Annotated[Mcp, tyro.conf.subcommand("mcp")]
    | Annotated[Version, tyro.conf.subcommand("version")]
)


def serve(cmd: Serve) -> None:
    try:
        import uvicorn

        from loupe.server import create_app
    except ImportError as exc:
        raise SystemExit(
            "loupe serve needs the server extra: pip install 'loupelab[server]'"
        ) from exc
    from loupe.server.app import LOOPBACK

    hosts = None
    if cmd.host not in LOOPBACK:
        if not cmd.expose:
            raise SystemExit(f"--host {cmd.host} serves every log without auth; add --expose")
        hosts = ["*"] if cmd.host in ("0.0.0.0", "::") else [*LOOPBACK, cmd.host]
    uvicorn.run(
        create_app(cmd.web_dir, hosts, launching=hosts is None),
        host=cmd.host,
        port=cmd.port,
    )


def main() -> None:
    match cmd := tyro.cli(Command):
        case Serve() as cmd:
            serve(cmd)
        case Data(cmd=sub):
            from loupe.data.cli import run

            run(sub)
        case TrainCommand():
            from loupe.train.cli import run as run_train

            run_train(cmd)
        case Sweep() as cmd:
            from loupe.sweep import sweep

            print(sweep(cmd.task, cmd.model, cmd.vector, cmd.layers, cmd.alphas, cmd.metric,
                        cmd.experiment))  # fmt: skip
        case Grid() as cmd:
            import inspect

            import yaml

            from loupe.grid import grid

            spec = yaml.safe_load(cmd.config.read_text(encoding="utf-8"))
            if unknown := set(spec) - set(inspect.signature(grid).parameters):
                raise SystemExit(f"{cmd.config}: unknown keys {sorted(unknown)}")
            print(grid(**spec))
        case New() as cmd:
            from loupe.stores.experiments import BadExperiment, scaffold

            try:
                print(f"created {scaffold(cmd.name, cmd.domain)}")
            except BadExperiment as exc:
                raise SystemExit(str(exc)) from exc
        case Features() as cmd:
            from loupe.features import features

            print(features(cmd.model, cmd.sae, cmd.sae_id, cmd.dataset, cmd.split, cmd.column,
                           cmd.n, cmd.max_tokens, list(cmd.features) or None, cmd.top_n, cmd.k,
                           cmd.experiment, cmd.revision))  # fmt: skip
        case Circuit() as cmd:
            from loupe.circuits import circuit

            circuit(cmd.model, cmd.transcoders, cmd.prompt, cmd.slug, cmd.dtype, cmd.batch_size)
        case Import() as cmd:
            from loupe.server.launch import Jobs
            from loupe.server.remote import import_result

            try:
                done = import_result(cmd.path, Jobs(work=False))
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            print(f"{len(done.runs)} runs from {done.host} (exit {done.exit_code})"
                  + (f", {len(done.skipped)} already here" if done.skipped else ""))  # fmt: skip
        case Bench() as cmd:
            from loupe.bench import bench
            from loupe.models.load import Quant

            quants: list[Quant | None] = [None if q == "none" else q for q in cmd.quants]
            print(bench(cmd.model, quants, tuple(cmd.batches), tuple(cmd.contexts),
                        cmd.new_tokens, cmd.repeats, cmd.experiment, cmd.draft,
                        cmd.profile))  # fmt: skip
        case Judge() as cmd:
            from loupe.judge import judge

            try:
                print(judge(cmd.a, cmd.b, cmd.model, cmd.criterion, cmd.limit, cmd.max_tokens))
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
        case Mcp() as cmd:
            try:
                from loupe.agent import server
            except ModuleNotFoundError as exc:
                if exc.name not in ("mcp", "mcp_types", "httpx"):
                    raise
                raise SystemExit(
                    "loupe mcp needs the agent extra: pip install 'loupelab[agent]'"
                ) from exc
            server(cmd.url).run("stdio")
        case Version():
            print(__version__)

"""The loupe command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import tyro

from loupe import __version__
from loupe.data.cli import Command as DataCommand
from loupe.train.cli import Command as TrainCommand


@dataclass(frozen=True)
class Serve:
    """Start the API and, when it has been built, the UI."""

    host: str = "127.0.0.1"
    port: int = 8000
    web_dir: Path = Path("apps/web/out")
    """The UI's static export; built by `just web-build`."""
    model: str | None = None
    """A model for the Playground: a Hub id, a path, or a name under <home>/models. Needs the
    interp extra."""
    bank: list[str] = field(default_factory=list)
    """Adapters to load beside the model, by name under <home>/adapters or path; the Playground
    picks which are live. Needs the train extra."""
    diffusion: bool = False
    """The model is a masked diffusion model (LLaDA, Dream, a masked LM), saved under
    <home>/models or at a path."""
    attn: str | None = None
    """The attention kernel: eager, sdpa, flash_attention_2, flex_attention, a registered name, or
    file.py:function. Attention views run eager for their own trace."""
    expose: bool = False
    """Allow a host other than this machine. There is no auth: whoever reaches the port reads
    every run, log and transcript."""


@dataclass(frozen=True)
class Data:
    """Training sets from a product's model calls: export, verify, review, curate, stats."""

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
class Version:
    """Print the installed version."""


Command = (
    Annotated[Serve, tyro.conf.subcommand("serve")]
    | Annotated[Data, tyro.conf.subcommand("data")]
    | Annotated[TrainCommand, tyro.conf.subcommand("train")]
    | Annotated[Sweep, tyro.conf.subcommand("sweep")]
    | Annotated[Grid, tyro.conf.subcommand("grid")]
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
        create_app(cmd.web_dir, cmd.model, hosts, cmd.bank, cmd.diffusion, cmd.attn),
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
        case Version():
            print(__version__)

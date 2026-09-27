"""The loupe command."""

from __future__ import annotations

from dataclasses import dataclass
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
class Version:
    """Print the installed version."""


Command = (
    Annotated[Serve, tyro.conf.subcommand("serve")]
    | Annotated[Data, tyro.conf.subcommand("data")]
    | Annotated[TrainCommand, tyro.conf.subcommand("train")]
    | Annotated[Sweep, tyro.conf.subcommand("sweep")]
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
    uvicorn.run(create_app(cmd.web_dir, cmd.model), host=cmd.host, port=cmd.port)


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
        case Version():
            print(__version__)

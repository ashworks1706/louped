"""The loupe command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import tyro

from loupe import __version__


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
class Version:
    """Print the installed version."""


Command = (
    Annotated[Serve, tyro.conf.subcommand("serve")]
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
    match tyro.cli(Command):
        case Serve() as cmd:
            serve(cmd)
        case Version():
            print(__version__)

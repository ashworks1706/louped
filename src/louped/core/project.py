"""The research project a command runs in.

A project is a folder with a louped.toml at its top: its experiments/ beside it, its state in
.louped/. Commands find it from the working directory upward, as git finds .git, so they work from
any subfolder. Outside a project, the working directory stands in for it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

#: The file that marks a project's root and holds its settings.
FILE = "louped.toml"


def root(start: Path | None = None) -> Path | None:
    """The nearest folder at or above start (the working directory) holding louped.toml."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / FILE).is_file():
            return folder
    return None


def base() -> Path:
    """Where a project's experiments/ and .louped/ sit: its root, else the working directory."""
    return root() or Path.cwd()


def config() -> dict[str, Any]:
    """The project's louped.toml, or nothing outside a project. A file that does not parse is an
    error naming it, not an empty config."""
    found = root()
    if found is None:
        return {}
    path = found / FILE
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: {exc}") from exc

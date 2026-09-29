"""What a run records about the world it ran in, so its numbers can be reproduced.

A result without the commit, the package versions and the seed it came from cannot be trusted
later, so every run writes one of these next to its outputs.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel

#: Packages whose version changes results. Missing ones are recorded as absent, not skipped.
TRACKED = (
    "loupelab",
    "torch",
    "transformers",
    "nnsight",
    "inspect-ai",
    "trl",
    "peft",
)


class Git(BaseModel):
    """The commit a run came from, and whether the tree had uncommitted changes."""

    sha: str | None
    dirty: bool


class RunMeta(BaseModel):
    """Everything about a run's environment that can move its numbers."""

    started_at: datetime
    python: str
    platform: str
    git: Git
    packages: dict[str, str | None]
    seed: int | None = None

    def write(self, path: Path) -> None:
        """Write as JSON, creating the directory."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def git_state(cwd: Path | None = None) -> Git:
    """The HEAD commit and dirty flag; a sha of None outside a repository or before a commit."""
    where = cwd or Path.cwd()
    sha = _git(["rev-parse", "HEAD"], where)
    status = _git(["status", "--porcelain"], where)
    return Git(sha=sha or None, dirty=bool(status))


def packages(names: tuple[str, ...] = TRACKED) -> dict[str, str | None]:
    """Installed version of each package, None when it is not installed."""
    found: dict[str, str | None] = {}
    for name in names:
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            found[name] = None
    return found


def capture(seed: int | None = None, cwd: Path | None = None) -> RunMeta:
    """The environment of a run starting now."""
    return RunMeta(
        started_at=datetime.now(UTC),
        python=sys.version.split()[0],
        platform=platform.platform(),
        git=git_state(cwd),
        packages=packages(),
        seed=seed,
    )

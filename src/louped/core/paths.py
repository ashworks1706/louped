"""Where louped and the tools it drives keep what they write.

Everything lives under one state directory so a run, its eval logs and its tracking database can
be moved or deleted together: .louped/ at the project's root (louped.core.project), beside its
experiments/. Each tool's own environment variable still wins when it is set.
"""

import os
import re
from pathlib import Path

from louped.core.project import base


def home() -> Path:
    """The state directory: LOUPED_HOME when set, else .louped at the project's root."""
    return Path(os.environ.get("LOUPED_HOME", base() / ".louped")).resolve()


def logs_dir() -> Path:
    """Inspect's eval logs: INSPECT_LOG_DIR when set, else <home>/logs."""
    return Path(os.environ.get("INSPECT_LOG_DIR", home() / "logs")).resolve()


def tracking_uri() -> str:
    """MLflow's store: MLFLOW_TRACKING_URI when set, else a SQLite file under home."""
    return os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{home() / 'mlflow.db'}")


def saved_model(name: str) -> Path | None:
    """The model saved as <home>/models/<name> (a fine-tune, a test model), or None."""
    local = home() / "models" / name
    return local if (local / "config.json").exists() else None


def artifacts_dir() -> Path:
    """Where MLflow runs started by louped put their artifacts."""
    return home() / "artifacts"


def vectors_dir() -> Path:
    """Saved directions, one safetensors file each."""
    return home() / "vectors"


def adapters_dir() -> Path:
    """Named PEFT adapters, one directory each, for the adapter bank."""
    return home() / "adapters"


def graphs_dir() -> Path:
    """circuit-tracer's attribution graphs and, under viewer/, its frontend (louped circuit)."""
    return home() / "graphs"


def experiments_dir() -> Path:
    """The research questions: LOUPED_EXPERIMENTS when set, else experiments/ at the project's
    root."""
    return Path(os.environ.get("LOUPED_EXPERIMENTS", base() / "experiments")).resolve()


def trash(path: Path, kind: str) -> Path:
    """Move a file or folder louped deletes to <home>/trash/<kind>/, stamped, instead of removing
    it: a deletion from the app is undone by moving it back. Returns where it went."""
    import shutil
    from datetime import UTC, datetime

    target = home() / "trash" / kind / f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{path.name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(path, target)
    return target


#: A name louped files a thing under (a cohort, a figure, a derived file): lowercase letters,
#: digits and -.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def inside(root: Path, *parts: str) -> Path:
    """root/parts, refused (ValueError) when it would lead out of root: a name with .. or a /."""
    base_ = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base_, *parts))
    if not path.startswith(base_ + os.sep):
        raise ValueError(f"{'/'.join(parts)!r} is not a name under {root}")
    return Path(path)


def experiment_folder(experiment: str) -> Path:
    """An experiment's folder, directly under experiments/ with its README; FileNotFoundError
    when there is none."""
    folder = inside(experiments_dir(), experiment)
    if (
        folder.parent != Path(os.path.realpath(experiments_dir()))
        or not (folder / "README.md").is_file()
    ):
        raise FileNotFoundError(f"no experiment {experiment!r} under {experiments_dir()}")
    return folder

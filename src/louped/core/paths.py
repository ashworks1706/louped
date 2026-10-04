"""Where louped and the tools it drives keep what they write.

Everything lives under one state directory so a run, its eval logs and its tracking database can
be moved or deleted together: .louped/ at the project's root (louped.core.project), beside its
experiments/. Each tool's own environment variable still wins when it is set.
"""

import os
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

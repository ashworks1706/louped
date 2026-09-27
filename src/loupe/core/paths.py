"""Where loupe and the tools it drives keep what they write.

Everything lives under one state directory so a run, its eval logs and its tracking database can
be moved or deleted together. Each tool's own environment variable still wins when it is set.
"""

import os
from pathlib import Path


def home() -> Path:
    """The state directory: LOUPE_HOME when set, else .loupe under the working directory."""
    return Path(os.environ.get("LOUPE_HOME", ".loupe")).resolve()


def logs_dir() -> Path:
    """Inspect's eval logs: INSPECT_LOG_DIR when set, else <home>/logs."""
    return Path(os.environ.get("INSPECT_LOG_DIR", home() / "logs")).resolve()


def tracking_uri() -> str:
    """MLflow's store: MLFLOW_TRACKING_URI when set, else a SQLite file under home."""
    return os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{home() / 'mlflow.db'}")


def artifacts_dir() -> Path:
    """Where MLflow runs started by loupe put their artifacts."""
    return home() / "artifacts"


def experiments_dir() -> Path:
    """The research questions: LOUPE_EXPERIMENTS when set, else ./experiments."""
    return Path(os.environ.get("LOUPE_EXPERIMENTS", "experiments")).resolve()

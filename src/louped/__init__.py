"""louped: a local workbench for research on LLM behavior and efficiency."""

import os
from importlib.metadata import PackageNotFoundError, version

# MLflow prints a hint for coding agents on import; louped's scripts run outside `just` too.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

try:
    __version__ = version("louped")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.6.0"  # release-please sets this with pyproject.toml's version

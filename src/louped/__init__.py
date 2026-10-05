"""louped: a research testbed for looking inside language models."""

import os
from importlib.metadata import PackageNotFoundError, version

# MLflow prints a hint for coding agents on import; louped's scripts run outside `just` too.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

try:
    __version__ = version("louped")
except PackageNotFoundError:  # a source tree that was never installed: no version to claim
    __version__ = "0+unknown"

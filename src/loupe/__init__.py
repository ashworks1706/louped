"""loupe: a research testbed for looking inside language models."""

import os
from importlib.metadata import PackageNotFoundError, version

# MLflow prints a hint for coding agents on import; loupe's scripts run outside `just` too.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

try:
    __version__ = version("loupelab")
except PackageNotFoundError:
    __version__ = "0.0.0"

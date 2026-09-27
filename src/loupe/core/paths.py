"""Where loupe keeps what it writes."""

import os
from pathlib import Path


def home() -> Path:
    """The state directory: LOUPE_HOME when set, else .loupe under the working directory."""
    return Path(os.environ.get("LOUPE_HOME", ".loupe")).resolve()

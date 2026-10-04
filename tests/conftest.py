import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Tests are CPU only, so a machine with a GPU runs them as CI does.
os.environ["CUDA_VISIBLE_DEVICES"] = ""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Every test gets its own state directory, and no store env var leaks in."""
    home = tmp_path / "home"
    monkeypatch.setenv("LOUPED_HOME", str(home))
    monkeypatch.setenv("LOUPED_EXPERIMENTS", str(tmp_path / "experiments"))
    for var in ("INSPECT_LOG_DIR", "MLFLOW_TRACKING_URI"):
        monkeypatch.delenv(var, raising=False)
    # runs are milliseconds long here; the sampler is tested on its own (test_tracking)
    monkeypatch.setenv("LOUPED_SYSTEM_METRICS", "0")
    yield home


@pytest.fixture(autouse=True)
def offline_token_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inspect estimates tokens with tiktoken, which downloads its encoding; count words instead."""
    import inspect_ai.model._model as model
    import inspect_ai.model._tokens as tokens

    def words(text: str) -> int:
        return max(1, len(text.split()))

    monkeypatch.setattr(tokens, "count_text_tokens", words)
    monkeypatch.setattr(model, "count_text_tokens", words)

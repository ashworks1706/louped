"""One plain function, two uses: an Inspect scorer (loupe.inspect_ext.as_scorer) and a GRPO reward.

A check is `def check(completion: str, **row) -> float`: the reply's text and the sample's other
fields by name (a GRPO row's columns, or an Inspect sample's target and metadata). A check that
names only some fields gets only those.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from loupe.core import named_fields
from loupe.train.base import TrainError

Check = Callable[..., float]


def as_reward(check: Check) -> Callable[..., list[float]]:
    """A TRL reward function over a batch of completions and their dataset columns."""
    takes = named_fields(check)

    def reward(prompts: list[Any], completions: list[Any], **columns: Any) -> list[float]:
        out: list[float] = []
        for i, completion in enumerate(completions):
            text = completion[-1]["content"] if isinstance(completion, list) else str(completion)
            row = {k: v[i] for k, v in columns.items()
                   if isinstance(v, list) and len(v) == len(completions)}  # fmt: skip
            out.append(float(check(text, **takes(row))))
        return out

    reward.__name__ = check.__name__
    return reward


def load_check(spec: str, base: Path | None = None) -> Check:
    """A check named file.py:function (relative to base) or module:function."""
    target, _, name = spec.rpartition(":")
    if not target or not name:
        raise TrainError(f"reward {spec!r} is not file.py:function or module:function")
    if target.endswith(".py"):
        path = Path(target) if Path(target).is_absolute() or base is None else base / target
        loader = importlib.util.spec_from_file_location(path.stem, path)
        if loader is None or loader.loader is None or not path.exists():
            raise TrainError(f"no reward file at {path}")
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
    else:
        module = importlib.import_module(target)
    check: Any = getattr(module, name, None)
    if not callable(check):
        raise TrainError(f"{spec}: no function {name!r}")
    return cast(Check, check)

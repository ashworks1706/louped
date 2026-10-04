"""Calling a plain check with the fields it names: the shared rule of scorers and rewards."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def named_fields(check: Callable[..., Any]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """A filter that keeps the fields check names, or all of them when it takes **fields."""
    params = inspect.signature(check).parameters.values()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return lambda fields: fields
    names = {p.name for p in params}
    return lambda fields: {k: v for k, v in fields.items() if k in names}

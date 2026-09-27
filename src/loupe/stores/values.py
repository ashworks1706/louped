"""Turning score values of any shape into numbers the UI can aggregate."""

from __future__ import annotations

from typing import Any

#: Inspect's letter grades: correct, incorrect, partial, no answer.
GRADES = {"C": 1.0, "I": 0.0, "P": 0.5, "N": 0.0}


def to_float(value: Any) -> float | None:
    """A number for a score value, None when it has no numeric reading."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        if value in GRADES:
            return GRADES[value]
        try:
            return float(value)
        except ValueError:
            return None
    return None


def flatten(name: str, value: Any) -> dict[str, float | None]:
    """A score as one or more named numbers: a dict score becomes name.key entries."""
    if isinstance(value, dict):
        return {f"{name}.{k}": to_float(v) for k, v in value.items()}
    return {name: to_float(value)}


def text(value: Any, limit: int | None = None) -> str:
    """A readable string for an input or target of any shape."""
    if value is None:
        out = ""
    elif isinstance(value, str):
        out = value
    elif isinstance(value, list):
        parts = [getattr(m, "text", None) or str(m) for m in value]
        out = "\n".join(p for p in parts if p)
    else:
        out = str(value)
    return out if limit is None or len(out) <= limit else out[: limit - 1] + "…"

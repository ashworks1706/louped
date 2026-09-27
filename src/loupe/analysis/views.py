"""The shapes the Run page's Figures tab renders. A run stores each as JSON under views/ in MLflow.

Three kinds cover the standard figures: a heatmap (patching: layer by position; attention: one
slice per layer and head), a line chart (anything by layer), and a table (logit lens tokens).
Keeping them as data, not images, is what lets the UI hover, sort and link them.
"""

from __future__ import annotations

from typing import Any


def heatmap(
    title: str,
    z: list[list[float]],
    x: list[str],
    y: list[str],
    x_label: str,
    y_label: str,
    note: str | None = None,
    slices: dict[str, list[list[float]]] | None = None,
) -> dict[str, Any]:
    """With slices, named grids the UI switches between, the first shown first; z is that one."""
    return {
        "kind": "heatmap",
        "title": title,
        "x": x,
        "y": y,
        "z": z,
        "x_label": x_label,
        "y_label": y_label,
        "note": note,
        "slices": slices,
    }


def line(
    title: str,
    x: list[float],
    series: dict[str, list[float]],
    x_label: str,
    y_label: str,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "line",
        "title": title,
        "x": x,
        "series": series,
        "x_label": x_label,
        "y_label": y_label,
        "note": note,
    }


def table(
    title: str, columns: list[str], rows: list[list[Any]], note: str | None = None
) -> dict[str, Any]:
    return {"kind": "table", "title": title, "columns": columns, "rows": rows, "note": note}

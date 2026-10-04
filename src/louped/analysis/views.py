"""The shapes the Run page's Figures tab renders. A run stores each as JSON under views/ in MLflow.

Five kinds cover the standard figures: a heatmap (patching: layer by position; attention: one
slice per layer and head; the logit lens and a diffusion trajectory, each cell labelled with its
token), a line chart (anything by layer), a scatter (one labelled point per condition: quality
against cost), a table, and tokens (text coloured by a per-token value).
Keeping them as data, not images, is what lets the UI hover, sort and link them. Each takes
`about`: one or two sentences on how to read it, shown behind a ? beside its title.
"""

from __future__ import annotations

from typing import Any, Literal


def heatmap(
    title: str,
    z: list[list[float]],
    x: list[str],
    y: list[str],
    x_label: str,
    y_label: str,
    note: str | None = None,
    slices: dict[str, list[list[float]]] | None = None,
    labels: list[list[str]] | None = None,
    about: str | None = None,
) -> dict[str, Any]:
    """With slices, named grids the UI switches between, the first shown first; z is that one.

    With labels, shaped like z, each cell shows its text.
    """
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
        "labels": labels,
        "about": about,
    }


def by_head(
    title: str, z: list[list[float]], note: str | None = None, about: str | None = None
) -> dict[str, Any]:
    """A heatmap of z, one row per layer and one column per head."""
    heads = [str(j) for j in range(len(z[0]) if z else 0)]
    rows = [str(i) for i in range(len(z))]
    return heatmap(title, z, heads, rows, "head", "layer", note, about=about)


def line(
    title: str,
    x: list[float],
    series: dict[str, list[float]],
    x_label: str,
    y_label: str,
    note: str | None = None,
    about: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "line",
        "title": title,
        "x": x,
        "series": series,
        "x_label": x_label,
        "y_label": y_label,
        "note": note,
        "about": about,
    }


def scatter(
    title: str,
    points: list[tuple[str, float, float]],
    x_label: str,
    y_label: str,
    note: str | None = None,
    about: str | None = None,
) -> dict[str, Any]:
    """Labelled points, (label, x, y): one per condition, such as a score against its latency."""
    marks = [{"label": n, "x": x, "y": y} for n, x, y in points]
    return {"kind": "scatter", "title": title, "x_label": x_label, "y_label": y_label,
            "points": marks, "note": note, "about": about}  # fmt: skip


def table(
    title: str,
    columns: list[str],
    rows: list[list[Any]],
    note: str | None = None,
    links: list[list[str | None]] | None = None,
    embed: Literal["neuronpedia"] | None = None,
    about: str | None = None,
) -> dict[str, Any]:
    """A table; `links`, shaped like `rows`, turns a cell into a link to that URL. With
    embed="neuronpedia" the links are feature pages the UI opens embedded."""
    return {"kind": "table", "title": title, "columns": columns, "rows": rows, "note": note,
            "links": links, "embed": embed, "about": about}  # fmt: skip


def token_row(
    tokens: list[str], values: dict[str, list[float]], label: str | None = None
) -> dict[str, Any]:
    """One text: its tokens and named per-token series, each as long as tokens."""
    return {"tokens": tokens, "values": values, "label": label}


def tokens(
    title: str,
    rows: list[dict[str, Any]],
    note: str | None = None,
    pairs: dict[str, list[list[float]]] | None = None,
    about: str | None = None,
) -> dict[str, Any]:
    """Texts coloured per token by a series the UI picks.

    With pairs, one [token, token] grid per series name, the UI colours by the hovered token's row
    of the grid instead (attention: what a query token attends to). Pairs need a single row.
    """
    if pairs is not None and len(rows) != 1:
        raise ValueError("pairs need exactly one row")
    return {"kind": "tokens", "title": title, "rows": rows, "pairs": pairs, "note": note,
            "about": about}  # fmt: skip

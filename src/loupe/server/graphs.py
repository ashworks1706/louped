"""circuit-tracer's graph viewer at /circuit, with the files it asks for, all from <home>/graphs as
`just circuit` leaves it.

The viewer reads ./data/graph-metadata.json and ./graph_data/<slug>.json; circuit-tracer writes
both into the one folder, so both paths serve it. Before `just circuit` has run, all are 404.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from loupe.core import graphs_dir


def mount(app: FastAPI) -> None:
    root = graphs_dir()
    (root / "viewer").mkdir(parents=True, exist_ok=True)
    app.mount("/circuit/data", StaticFiles(directory=root), name="circuit-data")
    app.mount("/circuit/graph_data", StaticFiles(directory=root), name="circuit-graphs")
    app.mount("/circuit", StaticFiles(directory=root / "viewer", html=True), name="circuit")

"""circuit-tracer's attribution graphs, listed at /api/graphs and drawn by its own viewer at
/circuit, both from <home>/graphs as `just circuit` leaves it.

The viewer asks for ./data/graph-metadata.json and ./graph_data/<slug>.json; both are files
circuit-tracer wrote next to each other, so they are served from the one folder.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from loupe.core import graphs_dir


class Graph(BaseModel):
    slug: str
    prompt: str
    scan: str | None = None


def list_graphs() -> list[Graph]:
    """The graphs in circuit-tracer's metadata file, newest last; none when there is no file."""
    meta = graphs_dir() / "graph-metadata.json"
    if not meta.exists():
        return []
    return [Graph.model_validate(g) for g in json.loads(meta.read_text())["graphs"]]


def _file(name: str) -> FileResponse:
    path = graphs_dir() / name
    if "/" in name or ".." in name or not path.is_file():
        raise HTTPException(404, f"no graph file {name}")
    return FileResponse(path, media_type="application/json")


def mount(app: FastAPI) -> None:
    """/api/graphs, and the viewer at /circuit once `just circuit` has copied it there."""
    api = APIRouter()

    @api.get("/api/graphs")
    def graphs() -> list[Graph]:
        return list_graphs()

    @api.get("/circuit/data/{name}")
    def metadata(name: str) -> FileResponse:
        return _file(name)

    @api.get("/circuit/graph_data/{name}")
    def graph(name: str) -> FileResponse:
        return _file(name)

    app.include_router(api)
    viewer = StaticFiles(directory=graphs_dir() / "viewer", html=True, check_dir=False)
    app.mount("/circuit", viewer, name="circuit")

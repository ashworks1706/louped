"""The FastAPI app: the API under /api, and the built UI at / when there is one.

The server owns no database. Every route reads a store another tool already writes (MLflow,
Inspect logs, artifact files, experiments/), so deleting the server loses nothing.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from loupe import __version__, stores
from loupe.core import Direction, home
from loupe.server import playground
from loupe.stores.runs import read_artifact
from loupe.stores.types import (
    Experiment,
    RunDetail,
    RunSummary,
    RunView,
    SampleDetail,
    SampleSummary,
)

#: Where the UI's dev server runs; allowed to call the API during development only.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class Health(BaseModel):
    status: str
    version: str
    home: str


def create_app(web_dir: Path | None = None, model: str | None = None) -> FastAPI:
    """The app. With web_dir, the static UI export is served at /; with model, the Playground."""
    app = FastAPI(
        title="loupe",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(stores.NotFound)
    async def not_found(_: Request, exc: stores.NotFound) -> JSONResponse:
        return JSONResponse({"detail": f"not found: {exc}"}, status_code=404)

    @app.get("/api/health")
    def health() -> Health:
        return Health(status="ok", version=__version__, home=str(home()))

    @app.get("/api/runs")
    def runs() -> list[RunSummary]:
        return stores.list_runs()

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> RunDetail:
        return stores.get_run(run_id)

    @app.get("/api/runs/{run_id}/samples")
    def samples(run_id: str) -> list[SampleSummary]:
        return stores.list_samples(run_id)

    @app.get("/api/runs/{run_id}/samples/{sample_id}")
    def sample(run_id: str, sample_id: str, epoch: int = 1) -> SampleDetail:
        return stores.get_sample(run_id, sample_id, epoch)

    @app.get("/api/runs/{run_id}/artifacts/{path:path}")
    def artifact(run_id: str, path: str) -> Response:
        if ".." in Path(path).parts:
            raise HTTPException(400, "bad path")
        media = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return Response(read_artifact(run_id, path), media_type=media)

    @app.get("/api/runs/{run_id}/views")
    def views(run_id: str) -> list[RunView]:
        return stores.list_views(run_id)

    @app.get("/api/vectors")
    def vectors() -> list[Direction]:
        return stores.list_vectors()

    @app.get("/api/experiments")
    def experiments() -> list[Experiment]:
        return stores.list_experiments()

    app.include_router(playground.router(model))

    if web_dir is not None and web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app

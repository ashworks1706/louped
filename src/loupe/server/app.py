"""The FastAPI app: the API under /api, and the built UI at / when there is one.

The server owns no database. Every route reads a store another tool already writes (MLflow,
Inspect logs, artifact files), so deleting the server loses nothing.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from loupe import __version__
from loupe.core import home

#: Where the UI's dev server runs; allowed to call the API during development only.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class Health(BaseModel):
    status: str
    version: str
    home: str


def create_app(web_dir: Path | None = None) -> FastAPI:
    """The app. With web_dir, the static UI export is served at /."""
    app = FastAPI(
        title="loupe", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["GET"])

    @app.get("/api/health")
    def health() -> Health:
        return Health(status="ok", version=__version__, home=str(home()))

    if web_dir is not None and web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app

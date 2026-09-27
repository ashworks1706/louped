"""Inspect View, Inspect's own log viewer, served by loupe at /inspect over loupe's eval logs.

Its app calls /api/<route> on the page's origin; those routes do not collide with loupe's, so its
API is mounted at /api after loupe's routes and answers what they do not. Access is read-only and
confined to the log directory: the viewer cannot edit or delete a log.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from inspect_ai._util.asyncfiles import AsyncFilesystem
from inspect_ai._view._dist import resolve_dist_directory
from inspect_ai._view.fastapi_server import (
    AsyncFilesystemMiddleware,
    OnlyDirAccessPolicy,
    view_server_app,
)

from loupe.core import logs_dir


class _ReadOnly(OnlyDirAccessPolicy):
    async def can_write(self, request: Request, file: str) -> bool:
        return False

    async def can_delete(self, request: Request, file: str) -> bool:
        return False


def mount(app: FastAPI) -> None:
    """Add the viewer at /inspect and its API under /api. Call after loupe's own routes."""
    root = logs_dir()
    root.mkdir(parents=True, exist_ok=True)
    api = view_server_app(access_policy=_ReadOnly(str(root)), default_dir=str(root))
    app.mount("/api", AsyncFilesystemMiddleware(api, fs=AsyncFilesystem()))
    app.mount("/inspect", StaticFiles(directory=resolve_dist_directory(), html=True))

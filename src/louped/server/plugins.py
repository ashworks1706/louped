"""The project's plugins (louped.core.plugins) in the server: their routes under /api/x/<name>,
their panels at /x/<name>/, and the list the UI builds their sidebar entries from."""

from __future__ import annotations

import traceback
from types import ModuleType

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.routing import BaseRoute, Mount

from louped.core.plugins import Plugin, Section, find_plugins


class PluginInfo(BaseModel):
    name: str
    title: str
    section: Section
    description: str
    #: Whether it has a page of its own, at its sidebar entry (panel/index.html).
    panel: bool
    #: Whether it adds a tab to each run (run.html) and each experiment (experiment.html).
    run: bool = False
    experiment: bool = False
    #: Why its plugin.py did not load, shown on its page; null when it loaded or has none.
    error: str | None = None


def mount(app: FastAPI, launching: bool, pages: dict[str, list[str]]) -> None:
    """Load the plugins when launching is on, and list them; with --expose there are none. Call
    before Inspect View's catch-all /api mount. Fills pages with each mounted plugin's panel
    pages, which layouts may place.

    A plugin added while the server runs loads the next time the app lists the plugins: its
    routes and pages go in where the first ones did, ahead of the catch-all mounts. A change to a
    plugin.py that has loaded needs a restart; its pages are read afresh on each request."""
    at = len(app.router.routes)  # where plugins' routes go, ahead of what is mounted after
    loaded: dict[str, ModuleType | None] = {}
    errors: dict[str, str] = {}
    served: set[str] = set()

    def insert(route: BaseRoute) -> None:
        nonlocal at
        app.router.routes.insert(at, route)
        at += 1

    def info(plugin: Plugin) -> PluginInfo:
        if plugin.name not in loaded:
            try:
                loaded[plugin.name] = module = plugin.load()
            except Exception:
                errors[plugin.name] = traceback.format_exc(limit=-3)
                print(f"plugin {plugin.name} did not load:\n{errors[plugin.name]}")
                loaded[plugin.name] = module = None
            if module is not None and (router := getattr(module, "router", None)) is not None:
                wrapper = APIRouter()
                wrapper.include_router(router, prefix=f"/api/x/{plugin.name}")
                for route in wrapper.routes:
                    insert(route)
        if plugin.panel is not None and plugin.name not in served:
            insert(Mount(f"/x/{plugin.name}", StaticFiles(directory=plugin.panel, html=True),
                         name=f"plugin-{plugin.name}"))  # fmt: skip
            served.add(plugin.name)
        pages[plugin.name] = sorted(f.name for f in (plugin.folder / "panel").glob("*.html"))
        return PluginInfo(name=plugin.name, title=plugin.title, section=plugin.section,
                          description=plugin.description,
                          panel="index" in plugin.pages, run="run" in plugin.pages,
                          experiment="experiment" in plugin.pages,
                          error=errors.get(plugin.name))  # fmt: skip

    def scan() -> list[PluginInfo]:
        return [info(plugin) for plugin in find_plugins()] if launching else []

    scan()

    @app.get("/api/plugins")
    def plugins() -> list[PluginInfo]:
        return scan()

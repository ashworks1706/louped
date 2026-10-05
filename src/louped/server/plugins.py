"""The project's plugins (louped.core.plugins) in the server: their routes under /api/x/<name>,
their panels at /x/<name>/, and the list the UI builds their sidebar entries from."""

from __future__ import annotations

import traceback

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from louped.core.plugins import Section, find_plugins


class PluginInfo(BaseModel):
    name: str
    title: str
    section: Section
    description: str
    #: Whether it has a panel to show at its sidebar entry.
    panel: bool
    #: Why its plugin.py did not load, shown on its page; null when it loaded or has none.
    error: str | None = None


def mount(app: FastAPI, launching: bool) -> None:
    """Load the plugins when launching is on, and list them; with --expose there are none. Call
    before Inspect View's catch-all /api mount."""
    found: list[PluginInfo] = []
    for plugin in find_plugins() if launching else []:
        info = PluginInfo(name=plugin.name, title=plugin.title, section=plugin.section,
                          description=plugin.description,
                          panel=plugin.panel is not None)  # fmt: skip
        try:
            module = plugin.load()
        except Exception:
            info.error = traceback.format_exc(limit=-3)
            print(f"plugin {plugin.name} did not load:\n{info.error}")
            module = None
        if module is not None and (router := getattr(module, "router", None)) is not None:
            app.include_router(router, prefix=f"/api/x/{plugin.name}")
        if plugin.panel is not None:
            app.mount(f"/x/{plugin.name}", StaticFiles(directory=plugin.panel, html=True),
                      name=f"plugin-{plugin.name}")  # fmt: skip
        found.append(info)

    @app.get("/api/plugins")
    def plugins() -> list[PluginInfo]:
        return found

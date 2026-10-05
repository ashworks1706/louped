"""A project's own additions to louped, so a feature need not wait for a release.

A plugin is a folder under the project's plugins/ with a plugin.toml:

    title = "Verdicts"          # its name in the sidebar
    section = "behavior"        # workspace, behavior or efficiency: whose sidebar lists it
    description = "..."         # one line, for the command menu

and any of:

- plugin.py, the project's own code, which may define
  - `router`, a FastAPI APIRouter, served at /api/x/<name>;
  - `main(argv: list[str])`, run as `louped <name> ...`;
  - `tools(mcp, api)`, adding MCP tools to `louped mcp`; api is its httpx client of the server, so
    a tool calls the plugin's routes as `api.get("/x/<name>/...")`.
- panel/, static pages served at /x/<name>/ that call the same API the app does:
  - index.html, shown at the plugin's sidebar entry;
  - run.html, a tab on every run's page, opened with ?run=<run id>;
  - experiment.html, a tab on every experiment's page, opened with ?experiment=<name>.
  The app hands each its theme: the CSS variables (var(--foreground), var(--border), ...) and the
  `dark` class.

plugin.py runs in louped's own process, like an experiment's code, and only where launching is on:
never with `--expose` or in a published dashboard.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

from louped.core.project import base

Section = Literal["workspace", "behavior", "efficiency"]
Page = Literal["index", "run", "experiment"]
PAGES: tuple[Page, ...] = ("index", "run", "experiment")
NAME = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass
class Plugin:
    name: str
    folder: Path
    title: str
    section: Section
    description: str

    @property
    def code(self) -> Path | None:
        found = self.folder / "plugin.py"
        return found if found.is_file() else None

    @property
    def panel(self) -> Path | None:
        """panel/, when it holds any of the pages the app shows."""
        found = self.folder / "panel"
        return found if self.pages else None

    @property
    def pages(self) -> list[Page]:
        """Which of index.html, run.html and experiment.html panel/ has."""
        found = self.folder / "panel"
        return [p for p in PAGES if (found / f"{p}.html").is_file()]

    def load(self) -> ModuleType | None:
        """plugin.py imported, once; None when the plugin has none. Its errors are raised."""
        if self.code is None:
            return None
        module_name = f"louped_plugin_{self.name.replace('-', '_')}"
        if module_name in sys.modules:
            return sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, self.code)
        if spec is None or spec.loader is None:
            raise ImportError(f"{self.code} cannot be imported")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[module_name]
            raise
        return module


def plugins_dir() -> Path:
    return base() / "plugins"


def find_plugins() -> list[Plugin]:
    """The project's plugins, by name. A folder without plugin.toml is not one; a plugin.toml
    that is wrong is an error naming it."""
    root = plugins_dir()
    if not root.is_dir():
        return []
    found: list[Plugin] = []
    for folder in sorted(p for p in root.iterdir() if (p / "plugin.toml").is_file()):
        path = folder / "plugin.toml"
        if not NAME.match(folder.name):
            raise ValueError(f"{folder}: a plugin's folder name is lowercase letters, digits and -")
        try:
            meta = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"{path}: {exc}") from exc
        section = meta.get("section", "workspace")
        if section not in ("workspace", "behavior", "efficiency"):
            raise ValueError(f"{path}: section is workspace, behavior or efficiency")
        title = str(meta.get("title", folder.name))
        about = str(meta.get("description", ""))
        found.append(Plugin(folder.name, folder, title, section, about))
    return found

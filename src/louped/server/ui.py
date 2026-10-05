"""The app's pages as data, so a person's agent can rearrange them without a louped release.

A page is made of regions (run.tabs, run.overview, ...), and a region is a list of blocks from a
fixed catalog: metrics, report, a run's file, a figure, a plugin's page, and the rest. What each
region shows comes from, most specific first:

1. experiments/<name>/layout.json, for that experiment's page and its runs' pages;
2. layout.json at the project's root;
3. the preset either file names (`"preset": "eval"`), else the default.

    {"preset": "eval",
     "regions": {"run.overview": [{"block": "metrics"}, {"block": "file", "path": "examples.md"}]}}

A file that does not check is reported, by file and block, and not used: the page shows the
error over the layout below it. The theme is louped.toml's [theme]: its token values (`radius`,
and under [theme.light] and [theme.dark] the colours of src/app/globals.css) over the defaults.

Inside the blocks, every part of a page (a card, a row, a field, a control) has an address, and
a layout's "parts" change them by address (louped.server.parts). A person Shift+clicks parts to
hand them to their agent (ui_selection); the agent points back at them with ui_show.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from louped.core import experiments_dir
from louped.core.project import FILE, base, config
from louped.server import parts as parts_
from louped.server.launch import require_json
from louped.server.parts import KINDS, Cue, Cues, PartRule, Seen, Selection, ShowRequest

Region = Literal["home", "run.tabs", "run.overview", "experiment.tabs", "experiment.design"]
REGIONS: tuple[Region, ...] = (
    "home",
    "run.tabs",
    "run.overview",
    "experiment.tabs",
    "experiment.design",
)
#: The file a project or an experiment keeps its layout in.
LAYOUT = "layout.json"


class Block(BaseModel):
    """One piece of a region. Only the fields its kind needs are set."""

    model_config = ConfigDict(extra="forbid")

    block: str
    #: Its heading (or tab name) instead of the built-in one.
    title: str | None = None
    #: What its ? says: how to read it.
    about: str | None = None
    #: full: the region's width; half: two side by side; side: a narrow column beside the rest.
    width: Literal["full", "half", "side"] = "full"
    #: metric: the metric's name.
    key: str | None = None
    #: file: the run's file, as listed under its artifacts.
    path: str | None = None
    #: figure: its index among the run's figures.
    index: int | None = None
    #: plugin: the plugin's name, and which of its panel/ pages (default: the region's own).
    plugin: str | None = None
    page: str | None = None
    #: text: Markdown written into the layout itself, such as a note on how to read a page.
    text: str | None = None


class Layout(BaseModel):
    """A layout.json."""

    model_config = ConfigDict(extra="forbid")

    preset: str | None = None
    regions: dict[Region, list[Block]] = {}
    #: Changes to the parts inside the blocks, by address (louped.server.parts).
    parts: dict[str, PartRule] = {}


class Kind(BaseModel):
    block: str
    about: str
    #: The fields it needs.
    needs: list[str] = []


class Page(BaseModel):
    """What a page shows, region by region, and where each region came from."""

    regions: dict[Region, list[Block]]
    #: default, a preset's name, layout.json or experiments/<name>/layout.json.
    sources: dict[Region, str]
    #: Problems in the layout files, each naming its file; a file with any is not used.
    errors: list[str]
    #: The files that would set this page: the project's, and the experiment's when there is one.
    files: list[str]
    #: Changes to parts, by address: the experiment's keys over the project's.
    parts: dict[str, PartRule]


class Catalog(BaseModel):
    regions: dict[Region, list[Kind]]
    presets: dict[str, str]
    #: Every kind of part by its address, and the rules each takes.
    parts: list[parts_.Kind]


class Theme(BaseModel):
    """Token values over the defaults, for light and dark mode; errors name what was dropped."""

    light: dict[str, str]
    dark: dict[str, str]
    errors: list[str]


class SetRegion(BaseModel):
    #: The experiment whose layout.json to change; none: the project's.
    experiment: str | None = None
    region: Region
    #: The region's blocks; null removes it from the file, back to the preset or default.
    blocks: list[Block] | None


class SetPreset(BaseModel):
    experiment: str | None = None
    #: A preset's name; "default" for none, over a broader file's; null to name none here.
    preset: str | None


class SetPart(BaseModel):
    experiment: str | None = None
    #: A part's address; * for any one name.
    part: str = Field(max_length=300)
    #: Its rule; null removes it from the file.
    rule: PartRule | None


PLUGIN = Kind(block="plugin", about="A plugin's page from its panel/.", needs=["plugin"])
TEXT = Kind(block="text", about="Markdown written in the layout: a note, a link.", needs=["text"])

CATALOG: dict[Region, list[Kind]] = {
    "home": [
        Kind(block="stats", about="Live now, active questions, answered, runs this week."),
        Kind(block="live", about="Jobs and runs going now; absent when none are."),
        Kind(block="domains", about="The research domains, each with its count of questions."),
        Kind(block="active", about="The questions marked active."),
        Kind(block="latest", about="The newest runs."),
        TEXT,
        PLUGIN,
    ],
    "run.tabs": [
        Kind(block="overview", about="The run's overview region (run.overview)."),
        Kind(block="items", about="Every item under every condition; runs with per-item records."),
        Kind(block="figures", about="Every figure the run logged; runs with figures."),
        Kind(block="samples", about="An eval's samples and scores; evals only."),
        Kind(block="log", about="Inspect View on the eval's log; evals only."),
        Kind(block="artifacts", about="Every file the run wrote."),
        Kind(block="config", about="Parameters and tags."),
        Kind(block="file", about="One of the run's files as a tab of its own.", needs=["path"]),
        TEXT,
        PLUGIN,
    ],
    "run.overview": [
        Kind(block="error", about="The run's error; absent when it has none."),
        Kind(block="metrics", about="Every headline metric, one card each."),
        Kind(block="metric", about="One metric as a card of its own.", needs=["key"]),
        Kind(block="history", about="Metrics logged per step, as lines."),
        Kind(block="hardware", about="GPU and memory over the run; when it logged them."),
        Kind(block="report", about="report.md, rendered and editable; when the run wrote one."),
        Kind(block="file", about="One of the run's files, drawn for its kind.", needs=["path"]),
        Kind(block="figure", about="One of the run's figures.", needs=["index"]),
        Kind(block="provenance", about="Where and how the run was made."),
        TEXT,
        PLUGIN,
    ],
    "experiment.tabs": [
        Kind(block="design", about="The experiment's design region (experiment.design)."),
        Kind(block="runs", about="The experiment's runs."),
        TEXT,
        PLUGIN,
    ],
    "experiment.design": [
        Kind(block="readme", about="The README, rendered and editable."),
        Kind(block="result", about="The README's Result section."),
        Kind(block="runs", about="The experiment's runs."),
        TEXT,
        PLUGIN,
    ],
}

_b = Block
DEFAULT: dict[Region, list[Block]] = {
    "home": [_b(block=b) for b in ("stats", "live", "domains", "active", "latest")],
    "run.tabs": [
        _b(block=b)
        for b in ("overview", "items", "figures", "samples", "log", "artifacts", "config")
    ],
    "run.overview": [
        _b(block=b) for b in ("error", "metrics", "history", "hardware", "report", "provenance")
    ],
    "experiment.tabs": [_b(block="design"), _b(block="runs")],
    "experiment.design": [_b(block="readme"), _b(block="result", width="side")],
}

#: Starting points: each sets some regions, the default the rest.
PRESETS: dict[str, tuple[str, dict[Region, list[Block]]]] = {
    "eval": (
        "Opens a run on its items; the overview keeps the numbers and the report.",
        {
            "run.tabs": [
                _b(block=b)
                for b in ("items", "overview", "samples", "figures", "log", "artifacts", "config")
            ],
            "run.overview": [_b(block=b) for b in ("error", "metrics", "report", "provenance")],
        },
    ),
    "training": (
        "Curves first: history and hardware on the overview, figures before files.",
        {
            "run.tabs": [
                _b(block=b) for b in ("overview", "figures", "artifacts", "config", "log")
            ],
            "run.overview": [
                _b(block=b)
                for b in ("error", "history", "metrics", "hardware", "report", "provenance")
            ],
        },
    ),
    "focus": (
        "Only what answers the question: numbers, report, items, files.",
        {
            "home": [_b(block=b) for b in ("stats", "live", "active")],
            "run.tabs": [_b(block=b) for b in ("overview", "items", "artifacts")],
            "run.overview": [_b(block=b) for b in ("error", "metrics", "report")],
        },
    ),
}

#: A layout's preset that names the default, so an experiment can set aside the project's preset.
DEFAULT_PRESET = "default"

#: The page a plugin block opens when it names none.
PLUGIN_PAGE: dict[Region, str] = {
    "home": "index.html",
    "run.tabs": "run.html",
    "run.overview": "run.html",
    "experiment.tabs": "experiment.html",
    "experiment.design": "experiment.html",
}

#: The colours a theme may set: src/app/globals.css's, which plugin pages are handed too.
TOKENS = {
    "background", "foreground", "card", "card-foreground", "popover", "popover-foreground",
    "primary", "primary-foreground", "secondary", "secondary-foreground", "muted",
    "muted-foreground", "accent", "accent-foreground", "border", "input", "ring", "intervention",
    "positive", "negative",
}  # fmt: skip
#: A CSS value with nothing that could end the declaration or the rule it sits in.
VALUE = re.compile(r"^[#a-zA-Z0-9.,%/()\s+-]{1,80}$")
#: The functions a value may call: colours and lengths, never url() or anything that fetches.
FUNCTIONS = {"oklch", "oklab", "rgb", "rgba", "hsl", "hsla", "color-mix", "calc", "lab", "lch"}
CALLED = re.compile(r"([a-zA-Z-]*)\(")
PAGE_FILE = re.compile(r"^[a-z0-9-]+\.html$")


def _listed(name: str) -> Path | None:
    """The experiment's folder, as listed (a folder with a README.md), else None."""
    root = experiments_dir()
    if not root.is_dir():
        return None
    return next((f for f in root.iterdir() if f.name == name and (f / "README.md").is_file()), None)


def _experiment_folder(name: str) -> Path:
    found = _listed(name)
    if found is None:
        raise HTTPException(404, f"no experiment {name}")
    return found


def _file(experiment: str | None) -> tuple[Path, str]:
    """A layout file and how to name it to a person."""
    if experiment is None:
        return base() / LAYOUT, LAYOUT
    return _experiment_folder(experiment) / LAYOUT, f"experiments/{experiment}/{LAYOUT}"


def check(layout: Layout, plugins: dict[str, list[str]] | None) -> list[str]:
    """What is wrong with a layout: unknown blocks and presets, missing fields, plugins and pages
    that are not there. plugins maps each plugin to its panel pages; None skips plugin checks,
    for a server whose plugins are off."""
    errors = parts_.check(layout.parts)
    if (
        layout.preset is not None
        and layout.preset != DEFAULT_PRESET
        and layout.preset not in PRESETS
    ):
        names = ", ".join([*PRESETS, DEFAULT_PRESET])
        errors.append(f"preset {layout.preset!r} is not one of {names}")
    for region, blocks in layout.regions.items():
        kinds = {k.block: k for k in CATALOG[region]}
        tabs: dict[str, int] = {}
        for i, b in enumerate(blocks):
            at = f"{region}[{i}]"
            if region.endswith(".tabs") and b.block != "text":
                tab = f"{b.block}:{b.plugin or b.path or ''}"
                if tab in tabs:
                    errors.append(f"{at}: the same tab as {region}[{tabs[tab]}]")
                tabs.setdefault(tab, i)
            kind = kinds.get(b.block)
            if kind is None:
                errors.append(f"{at}: {b.block!r} is not a block of {region}: {', '.join(kinds)}")
                continue
            errors += [f"{at}: {b.block} needs {n}" for n in kind.needs if getattr(b, n) is None]
            if b.page is not None and not PAGE_FILE.match(b.page):
                errors.append(f"{at}: page {b.page!r} is not a file name like run.html")
            if b.block == "plugin" and b.plugin is not None and plugins is not None:
                page = b.page or PLUGIN_PAGE[region]
                if b.plugin not in plugins:
                    errors.append(f"{at}: no plugin {b.plugin!r} under plugins/")
                elif page not in plugins[b.plugin]:
                    errors.append(f"{at}: plugins/{b.plugin}/panel/{page} does not exist")
    return errors


def _read(
    path: Path, name: str, plugins: dict[str, list[str]] | None
) -> tuple[Layout | None, list[str]]:
    if not path.is_file():
        return None, []
    try:
        layout = Layout.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        return None, [f"{name}: {e['loc']}: {e['msg']}" for e in exc.errors(include_url=False)]
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"{name}: cannot be read: {exc}"]
    errors = check(layout, plugins)
    return (None, [f"{name}: {e}" for e in errors]) if errors else (layout, [])


def page(experiment: str | None, plugins: dict[str, list[str]] | None) -> Page:
    """The regions a page shows: an experiment's layout over the project's over a preset over
    the default. plugins are the pages of the plugins the server mounted, None where plugins are
    off, which leaves plugin blocks out."""
    files = [(base() / LAYOUT, LAYOUT)]
    if experiment is not None and (folder := _listed(experiment)):  # a run's may be gone
        files.insert(0, (folder / LAYOUT, f"experiments/{experiment}/{LAYOUT}"))
    errors: list[str] = []
    read = []
    for path, name in files:
        layout, problems = _read(path, name, plugins)
        errors += problems
        if layout is not None:
            read.append((layout, name))
    regions: dict[Region, list[Block]] = {}
    sources: dict[Region, str] = {}
    # the most specific file that names one; "default" there stops a broader file's
    preset = next((layout.preset for layout, _ in read if layout.preset), None)
    if preset == DEFAULT_PRESET:
        preset = None
    for region in REGIONS:
        found = next(((layout.regions[region], name) for layout, name in read
                      if region in layout.regions), None)  # fmt: skip
        if found is None and preset is not None and region in PRESETS[preset][1]:
            found = (PRESETS[preset][1][region], f"preset {preset}")
        blocks, source = found or (_default(region, plugins), "default")
        regions[region] = [b for b in blocks if b.block != "plugin" or plugins is not None]
        sources[region] = source
    merged: dict[str, PartRule] = {}
    for layout, _ in reversed(read):  # the project's, then the experiment's over it
        merged.update(layout.parts)
    return Page(regions=regions, sources=sources, errors=errors, parts=merged,
                files=[name for _, name in reversed(files)])  # fmt: skip


def _default(region: Region, plugins: dict[str, list[str]] | None) -> list[Block]:
    """The default, with a tab for each plugin that has a page for it, as before layouts."""
    blocks = list(DEFAULT[region])
    if region in ("run.tabs", "experiment.tabs") and plugins is not None:
        wanted = PLUGIN_PAGE[region]
        blocks += [Block(block="plugin", plugin=p) for p, has in plugins.items() if wanted in has]
    return blocks


def theme() -> Theme:
    """louped.toml's [theme]: radius for both modes, colours under [theme.light] and
    [theme.dark]. A token or value it cannot use is dropped and named in errors."""
    got = config().get("theme", {})
    light: dict[str, str] = {}
    dark: dict[str, str] = {}
    errors: list[str] = []
    if not isinstance(got, dict):
        return Theme(light=light, dark=dark, errors=[f"{FILE} theme: not a [theme] table"])

    def put(into: dict[str, str], where: str, token: str, value: object) -> None:
        plain = isinstance(value, str) and VALUE.match(value)
        if not plain or not set(CALLED.findall(str(value))) <= FUNCTIONS:
            errors.append(f"{FILE} [{where}] {token}: {value!r} is not a plain CSS value")
        else:
            into[token] = str(value)

    for key, value in got.items():
        if key in ("light", "dark") and isinstance(value, dict):
            for token, v in value.items():
                if token not in TOKENS:
                    errors.append(
                        f"{FILE} [theme.{key}] {token}: not a token: {', '.join(sorted(TOKENS))}"
                    )
                else:
                    put(light if key == "light" else dark, f"theme.{key}", token, v)
        elif key == "radius":
            put(light, "theme", key, value)
            if key in light:
                dark[key] = light[key]
        else:
            errors.append(f"{FILE} [theme] {key}: only radius, [theme.light] and [theme.dark]")
    return Theme(light=light, dark=dark, errors=errors)


def _write(path: Path, layout: Layout) -> None:
    data = layout.model_dump(exclude_defaults=True)
    if not data:
        path.unlink(missing_ok=True)
        return
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def router(launching: bool, mounted: dict[str, list[str]]) -> APIRouter:
    """The routes. mounted is filled by plugins.mount with what it served: each plugin's pages."""
    api = APIRouter(prefix="/api/ui")
    selected: list[Selection] = []
    cues: list[Cue] = []
    plugins = mounted if launching else None

    def editing() -> None:
        if not launching:
            raise HTTPException(403, "editing is off: this server was started with --expose")

    def current(experiment: str | None) -> tuple[Path, Layout]:
        path, name = _file(experiment)
        layout, errors = _read(path, name, plugins)
        if errors:
            raise HTTPException(422, "; ".join(errors) + f". Fix or delete {name} first.")
        return path, layout or Layout()

    @api.get("/layout")
    def layout(experiment: str | None = None) -> Page:
        return page(experiment, plugins)

    @api.get("/catalog")
    def catalog() -> Catalog:
        return Catalog(regions=CATALOG, presets={k: v[0] for k, v in PRESETS.items()}, parts=KINDS)

    @api.put("/layout", dependencies=[Depends(require_json)])
    def set_region(req: SetRegion) -> Page:
        """Sets one region of the project's or an experiment's layout.json, checked first."""
        editing()
        path, layout = current(req.experiment)
        if req.blocks is None:
            layout.regions.pop(req.region, None)
        else:
            layout.regions[req.region] = req.blocks
        if errors := check(layout, plugins):
            raise HTTPException(422, "; ".join(errors))
        _write(path, layout)
        return page(req.experiment, plugins)

    @api.put("/preset", dependencies=[Depends(require_json)])
    def set_preset(req: SetPreset) -> Page:
        editing()
        path, layout = current(req.experiment)
        layout.preset = req.preset
        if errors := check(layout, plugins):
            raise HTTPException(422, "; ".join(errors))
        _write(path, layout)
        return page(req.experiment, plugins)

    @api.put("/part", dependencies=[Depends(require_json)])
    def set_part(req: SetPart) -> Page:
        """Sets or removes one part's rule in the project's or an experiment's layout.json."""
        editing()
        path, layout = current(req.experiment)
        if req.rule is None:
            if layout.parts.pop(req.part, None) is None:
                raise HTTPException(404, f"no rule for {req.part} in {path}")
        else:
            layout.parts[req.part] = req.rule
        if errors := check(layout, plugins):
            raise HTTPException(422, "; ".join(errors))
        _write(path, layout)
        return page(req.experiment, plugins)

    @api.get("/theme")
    def get_theme() -> Theme:
        return theme()

    @api.post("/selection", dependencies=[Depends(require_json)])
    def select(req: Selection) -> Selection:
        """Keeps what the person has picked, replacing the last; in memory only."""
        editing()
        if sum(len(json.dumps(p.data)) for p in req.parts) > 200_000:
            raise HTTPException(413, "the picked parts' data is over 200 kB; pick fewer")
        selected[:] = [req]
        return req

    @api.get("/selection")
    def selection() -> Selection | None:
        return selected[0] if selected else None

    @api.post("/show", dependencies=[Depends(require_json)])
    def show(req: ShowRequest) -> Cue:
        """Queues something for the open app to show: a page, parts pointed at, a note."""
        editing()
        if bad := [p for p in req.parts if not parts_.ADDRESS.match(p)]:
            raise HTTPException(422, f"not a part's address: {', '.join(bad)}")
        cue = Cue(id=(cues[-1].id + 1) if cues else 1, at=time.time(), **req.model_dump())
        cues[:] = [*cues[-19:], cue]
        return cue

    @api.get("/show")
    def shown(after: int = 0) -> Cues:
        """The cues after one the app has, for the app to show."""
        return Cues(now=time.time(), cues=[c for c in cues if c.id > after])

    @api.get("/show/{cue}")
    def one_cue(cue: int) -> Cue:
        found = next((c for c in cues if c.id == cue), None)
        if found is None:
            raise HTTPException(404, f"no cue {cue}")
        return found

    @api.post("/show/{cue}/seen", dependencies=[Depends(require_json)])
    def seen(cue: int, req: Seen) -> Cue:
        """The app showed a cue; missing names the parts it could not find on the page."""
        editing()
        found = one_cue(cue)
        found.status = (
            "superseded"
            if req.superseded
            else "missing"
            if req.missing and len(req.missing) == len(found.parts)
            else "shown"
        )
        found.missing = req.missing
        return found

    return api

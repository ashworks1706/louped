"""Every part of a page by its address, what a layout may change about it, and the cues an agent
shows a person on it.

An address is "<area>/<kind>[/<name>...]": run/meta/model, items/stat/pressure,
items/row/28, item/field/evidence/second_turn. Names are URL-encoded, so a name with a / in it
(a folder, a file) stays one segment. Every part the app draws carries its address
(data-part), so a person can Shift+click it and their agent reads which with ui_selection.

A layout.json's "parts" changes parts by address; "*" in a key stands for any one segment:

    {"parts": {"item/field/*/abstain": {"hidden": true},
               "items/stat/pressure": {"label": "pushback", "note": "Read this one first."}}}

Each kind takes only the rules that mean something for it (KINDS). A block of a region is
changed in its region (set_layout), not here.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Rule = Literal["hidden", "label", "about", "note", "order", "default"]


class PartRule(BaseModel):
    """What a layout changes about the parts its key matches."""

    model_config = ConfigDict(extra="forbid")

    #: Not drawn.
    hidden: bool = False
    #: Its name on the page instead of the built-in one.
    label: str | None = Field(None, max_length=200)
    #: What its ? says.
    about: str | None = Field(None, max_length=2000)
    #: Markdown drawn under it: how to read it, what to look at first.
    note: str | None = Field(None, max_length=4000)
    #: Its place among its siblings (fields, columns, cards), lowest first; unset ones keep
    #: their order after the set ones.
    order: int | None = None
    #: A control's value when the page's URL sets none.
    default: str | None = Field(None, max_length=200)


class Kind(BaseModel):
    #: The address with * for a name.
    part: str
    about: str
    rules: list[Rule]


ALL: list[Rule] = ["hidden", "label", "about", "note", "order"]
LIST: list[Rule] = ["hidden", "label", "about", "order"]
NAME: list[Rule] = ["hidden", "label"]
CONTROL: list[Rule] = ["hidden", "label", "default"]
#: Picked to hand the agent its data; not changed by a layout.
PICK: list[Rule] = []

_k = Kind
KINDS: list[Kind] = [
    # the app around every page
    _k(part="panel/close", about="Closes a side panel.", rules=PICK),
    _k(part="shell/nav/*", about="A page in the sidebar, by its path.",
       rules=["hidden", "label", "order"]),
    _k(part="shell/domain/*", about="A section in the top bar: workspace, behavior, efficiency.",
       rules=["hidden", "label", "order"]),
    _k(part="shell/*", about="The top bar's home link, sidebar switch, jobs, search, status and "
       "theme switch.", rules=PICK),
    _k(part="page/*/title", about="A page's title, by its path (runs, behavior-vectors).",
       rules=["label"]),
    _k(part="page/*/description", about="A page's one-line purpose.", rules=["hidden", "label"]),
    # a run's page
    _k(part="run/title", about="The run's name.", rules=PICK),
    _k(part="run/back", about="The link back to Runs.", rules=["hidden"]),
    _k(part="run/badge/*", about="The run's kind, host, status, cohort or training alarm.",
       rules=["hidden"]),
    _k(part="run/meta/*", about="The run's model, experiment, created time or id.", rules=LIST),
    _k(part="run/delete", about="Moves the run to the trash.", rules=["hidden"]),
    _k(part="run.overview/metrics/*", about="One metric's card in the metrics block.",
       rules=ALL),
    _k(part="run.overview/hardware/*", about="One hardware number: gpu-energy, gpu-power, "
       "gpu-memory, ram.", rules=["hidden", "label", "about", "note"]),
    _k(part="run.overview/provenance/*", about="One fact of how the run was made: ran-on, code, "
       "seed, packages, command and the rest.", rules=LIST),
    # a run's items: every item under every condition
    _k(part="items/records", about="Which folder of per-item records to line up.",
       rules=CONTROL),
    _k(part="items/summary", about="The by-condition heading.", rules=["label", "note"]),
    _k(part="items/stat/*", about="One condition's rate (or changed count) and its flips.",
       rules=ALL),
    _k(part="items/search", about="Searches the items.", rules=["hidden"]),
    _k(part="items/compare", about="The field the conditions are compared on.", rules=CONTROL),
    _k(part="items/against", about="The reference condition.", rules=CONTROL),
    _k(part="items/show", about="Which items show: all, changed, changed:<c>, down:<c> (1→0), "
       "up:<c> (0→1).", rules=CONTROL),
    _k(part="items/cohort", about="Which items the conditions are read on: every item, the "
       "ones picked, or a cohort saved in the experiment.", rules=CONTROL),
    _k(part="items/cohort/note", about="The cohort's note, and its items no file holds.",
       rules=PICK),
    _k(part="items/count", about="How many items are shown.", rules=PICK),
    _k(part="items/download", about="Downloads the items shown.", rules=["hidden"]),
    _k(part="items/column/*", about="A column of the items table: the key, the text or a "
       "condition.", rules=LIST),
    _k(part="items/row/*", about="One item: its record in every condition.", rules=PICK),
    _k(part="items/cell/*/*", about="One item under one condition.", rules=PICK),
    _k(part="item/title", about="The open item's claim or question, under its id.", rules=PICK),
    _k(part="item/section/*", about="The item itself (item), or one condition's record of it.",
       rules=NAME),
    _k(part="item/field/*/*", about="One field of the item (section item) or of a condition's "
       "record.", rules=LIST),
    # one file's records, and one record
    _k(part="records/column/*", about="A column of a records table.", rules=LIST),
    _k(part="records/row/*", about="One record, by its place in the file.", rules=PICK),
    _k(part="records/filter/*", about="A filter on a column with few values.", rules=PICK),
    _k(part="records/*", about="A records table's search, count and download.", rules=PICK),
    _k(part="record/field/*", about="One field of an open record.", rules=LIST),
    # the training sets and one set's pairs
    _k(part="sets/column/*", about="A column of the training sets table.", rules=LIST),
    _k(part="sets/row/*", about="One training set, by its file's path.", rules=PICK),
    _k(part="set/stat/*", about="A count over the open set: pairs, or pairs with a flag; a flag's "
       "shows only those pairs.", rules=["hidden", "label", "about"]),
    _k(part="set/pair/*", about="One pair of the open set, by its row in the file.", rules=PICK),
    _k(part="set/*", about="The open set's title, warnings, labels and count.", rules=PICK),
    # an eval's samples
    _k(part="samples/column/*", about="A column of the samples table: #, input, target or a "
       "score.", rules=LIST),
    _k(part="samples/row/*", about="One sample (id, or id@epoch past the first).", rules=PICK),
    _k(part="samples/score/*", about="Shows only the samples that failed a score.", rules=PICK),
    _k(part="samples/degenerate/*", about="A share of degenerate replies (repeat, echo, loop); "
       "shows only those samples.", rules=["hidden", "label", "about"]),
    _k(part="samples/*", about="The samples' search, count, judge agreement and the readers "
       "disagree filter.", rules=PICK),
    _k(part="sample/*", about="The open sample's title, log link, model input heading and your "
       "pick.", rules=PICK),
    _k(part="sample/input/*", about="What one model call of the open sample read, by call number, "
       "special tokens included.", rules=PICK),
    _k(part="sample/score/*", about="One score of the open sample, with the rule that read it.",
       rules=PICK),
    # figures, config, files
    _k(part="figures/figure/*", about="One figure, by its file.", rules=["hidden", "note"]),
    _k(part="board/*", about="A board shown as a page of its own, by its name.", rules=PICK),
    _k(part="board/*/panel/*", about="One panel of a board, by the board's name and the "
       "panel's id: its rows as drawn.", rules=PICK),
    _k(part="board/*/control/*", about="One control of a board, by its param.", rules=PICK),
    _k(part="figures/export/*", about="Exports one figure to reports/ as SVG, PNG or PDF.",
       rules=PICK),
    _k(part="figures/code/*", about="Opens the script that made one figure, at its commit, on "
       "the forge.", rules=PICK),
    _k(part="config/param/*", about="One parameter.", rules=["hidden", "about", "order"]),
    _k(part="config/tag/*", about="One tag.", rules=["hidden", "about", "order"]),
    _k(part="config/*", about="The parameters' or tags' heading (params, tags).", rules=PICK),
    _k(part="artifacts/file/*", about="One of the run's files.", rules=PICK),
    _k(part="artifacts/folder/*", about="A folder of the run's files.", rules=PICK),
    _k(part="artifacts/whole/*", about="A folder's JSONL files read as one.", rules=PICK),
    _k(part="artifacts/*", about="The file filter and the open file.", rules=PICK),
    # an experiment's page and the lists of them
    _k(part="experiment/meta/*", about="The experiment's axis, domain, runs or last run.",
       rules=LIST),
    _k(part="experiment/launch/*", about="Opens Launch on one of the experiment's scripts.",
       rules=PICK),
    _k(part="experiment/view/*", about="A figure an agent added to the experiment's page, by "
       "its file (views/<name>.json).", rules=["hidden", "note", "order"]),
    _k(part="experiment/delete", about="Moves the experiment to the trash.", rules=["hidden"]),
    _k(part="experiment/gate/*", about="One requirement of the experiment's gate, by its metric, "
       "with its value and PASS or FAIL.", rules=PICK),
    _k(part="experiment/*", about="The experiment's name, status, question and back link.",
       rules=PICK),
    _k(part="experiments/row/*", about="One experiment in a list.", rules=PICK),
    _k(part="experiments/domain/*", about="A domain's heading in a list.", rules=PICK),
    _k(part="experiments/filter/*", about="A status filter: all, active, answered, parked.",
       rules=PICK),
    # runs tables
    _k(part="runs/column/*", about="A column of a runs table: select, run, kind, model, "
       "headline, status, created.", rules=LIST),
    _k(part="runs/row/*", about="One run in a runs table.", rules=PICK),
    _k(part="runs/filter/*", about="A runs filter: search, kind, experiment, status, clear.",
       rules=PICK),
    _k(part="runs/*", about="Runs' count and Compare.", rules=PICK),
    _k(part="runs/action/*", about="Runs' push, pull, connect, import and launch.",
       rules=["hidden"]),
    _k(part="runs/heading/*", about="The Jobs or Runs heading on Runs.", rules=PICK),
    _k(part="runs/job/*", about="One job in the queue.", rules=PICK),
    # home
    _k(part="home/stat/*", about="One of Home's numbers: live, active, answered, week.",
       rules=ALL),
    _k(part="home/live/*/*", about="A job or run going now.", rules=PICK),
    _k(part="home/live/title", about="The Running heading.", rules=PICK),
    _k(part="home/domain/*", about="A research domain's card.", rules=PICK),
    _k(part="home/more/*", about="A link to every experiment or run.", rules=["hidden"]),
    # any page
    _k(part="empty/*", about="What a page or panel shows before it has data, by its title "
       "(no-runs-yet), and what fills it.", rules=["note"]),
    # a domain's front page
    _k(part="domain/section/*", about="Tools, questions or runs on a domain's front page.",
       rules=["hidden", "note"]),
    _k(part="domain/tool/*", about="A tool's card, by its page (probe, vectors, benchmark).",
       rules=PICK),
    # Probe and Benchmark
    _k(part="playground/load", about="Loading a model, before one is loaded.", rules=["note"]),
    _k(part="playground/field/*", about="One control: model, adapters, intervention, vector, "
       "strength, layer, heads, tokens, method, follow-up, answer, foil, points and the rest.",
       rules=["hidden", "label", "about", "note"]),
    _k(part="playground/prompt", about="The prompt and Run.", rules=PICK),
    _k(part="playground/save", about="Keeps what the open tool showed as a run.",
       rules=["hidden"]),
    _k(part="playground/tab/*", about="A tool: reply, inspect, patch, dose, speed.",
       rules=["hidden", "label", "order"]),
    _k(part="playground/side/*", about="Which stream Inspect reads: base or intervention.",
       rules=PICK),
    _k(part="playground/reply/*", about="The base or intervened reply.", rules=PICK),
    _k(part="playground/figure/*", about="A figure a tool drew, by its title (logit-lens).",
       rules=["hidden", "note", "order"]),
    _k(part="playground/readout", about="Inspect's readout: every panel at the picked token.",
       rules=PICK),
    _k(part="playground/readout/tokens", about="The prompt's tokens: pick the position to read.",
       rules=PICK),
    _k(part="playground/readout/target", about="The token every panel follows, and its "
       "probability and rank at the output.", rules=PICK),
    _k(part="playground/readout/panel/*", about="A readout panel: lens, target, certainty, dla, "
       "heads.", rules=["hidden", "note"]),
    _k(part="playground/readout/cell", about="The lens cell under the cursor: its top tokens.",
       rules=PICK),
    _k(part="playground/readout/heads-metric", about="What the heads grid scores.", rules=PICK),
    _k(part="playground/readout/head", about="The picked head: what the token reads through it.",
       rules=PICK),
    # saved vectors
    _k(part="vectors/model/*", about="A model's heading over its vectors.", rules=PICK),
    _k(part="vectors/column/*", about="A column of the vectors table.", rules=PICK),
    _k(part="vectors/row/*", about="One saved vector, by name.", rules=PICK),
    _k(part="vectors/similar/*", about="How alike a model's vectors are: the cosine of each "
       "pair.", rules=["hidden", "note"]),
    # a metric over steps, on a run's page or two runs' on Compare
    _k(part="curves/metric/*", about="One metric's curve over steps.", rules=PICK),
    # attribution graphs
    _k(part="circuits/graph", about="Which graph is shown.", rules=PICK),
    _k(part="circuits/viewer", about="A link to the graph in circuit-tracer's own viewer.",
       rules=PICK),
    _k(part="circuits/prompt", about="The graph's prompt, token by token.", rules=PICK),
    _k(part="circuits/stat/*", about="One number about the graph: output, nodes, edges, "
       "unexplained.", rules=["hidden", "label", "about", "note"]),
    _k(part="circuits/prune/*", about="A slider: the share of influence the shown nodes or "
       "edges carry.", rules=PICK),
    _k(part="circuits/view", about="The pruned graph, or only the pinned nodes.", rules=PICK),
    _k(part="circuits/save", about="Saves the pins into the graph file.", rules=PICK),
    _k(part="circuits/canvas", about="The graph: token positions across, layers up.",
       rules=PICK),
    _k(part="circuits/node/*", about="One node of the graph, by circuit-tracer's node id.",
       rules=PICK),
    _k(part="circuits/legend", about="What the shapes and colours mean.", rules=["hidden"]),
    _k(part="circuits/panel", about="The side panel: the picked node, or the strongest ones.",
       rules=PICK),
    _k(part="circuits/node-detail/*", about="The picked node: influence, activation, inputs and "
       "outputs.", rules=PICK),
    _k(part="circuits/pin", about="Pins or unpins the picked node.", rules=PICK),
    _k(part="circuits/top", about="The outputs and the strongest features.", rules=PICK),
    _k(part="circuits/pinned", about="The pinned nodes and their groups.", rules=PICK),
    # an SAE feature
    _k(part="feature/figure/*", about="Promotes, suppresses, histogram or examples.",
       rules=["hidden", "note"]),
    _k(part="feature/*", about="The feature's title, back link, stepper and numbers.",
       rules=PICK),
    # Compare
    _k(part="compare/pick/*", about="Baseline (a), changed run (b), the swap and the judge.",
       rules=PICK),
    _k(part="compare/run/*", about="Run A or B's card.", rules=PICK),
    _k(part="compare/section/*", about="Metrics, curves, paired, samples or judge.",
       rules=["hidden", "note"]),
    _k(part="compare/metric/*", about="One metric of both runs.", rules=PICK),
    _k(part="compare/score/*", about="One score's paired difference and interval.", rules=PICK),
    _k(part="compare/sample/*", about="One sample in both runs.", rules=PICK),
    _k(part="compare/blind/*", about="Blind A/B: its button, progress, the request, the left or "
       "right answer, tie, reveal, the result and each judge's agreement.", rules=PICK),
    _k(part="compare/open/title", about="The open sample's title.", rules=PICK),
    _k(part="compare/open/side/*", about="The open sample in run A or B.", rules=PICK),
    # Sources
    _k(part="sources/search", about="Search the project's sources, every word.", rules=PICK),
    _k(part="sources/hit/*/*", about="One page a search found, by source key and page.",
       rules=PICK),
    _k(part="sources/source/*", about="One source in the list, by key.", rules=PICK),
    _k(part="sources/heading", about="The count of sources.", rules=PICK),
    _k(part="sources/table", about="The list of sources.", rules=["note"]),
    _k(part="sources/add", about="Adds a source: a file in the project or an https URL.",
       rules=["hidden", "note"]),
    _k(part="source/*", about="A source's viewer: its header, page controls, the page, Pin and, "
       "for a notebook, the whole notebook.",
       rules=PICK),
    _k(part="source/pin/*", about="One pinned passage of the source, by id.", rules=PICK),
    # Hub
    _k(part="hub/account", about="The Hugging Face account signed in here, or Connect.",
       rules=PICK),
    _k(part="hub/token", about="The token dialog's form.", rules=PICK),
    _k(part="hub/tab/*", about="Models, embeddings, datasets or papers.", rules=PICK),
    _k(part="hub/search", about="Search the Hub.", rules=PICK),
    _k(part="hub/filter/*", about="A search's task, library or sort.", rules=PICK),
    _k(part="hub/column/*", about="A column of the results.", rules=PICK),
    _k(part="hub/hit/*/*", about="One result, by kind and Hub id.", rules=PICK),
    _k(part="hub/detail/*", about="The open result's title, facts, card, abstract, links and "
       "actions.", rules=PICK),
    # Reports
    _k(part="reports/heading", about="The count of files in reports/.", rules=PICK),
    _k(part="reports/table", about="The files in reports/.", rules=["note"]),
    _k(part="reports/report/*", about="One file in reports/, by its path there.", rules=PICK),
    _k(part="reports/group/*", about="The reports on one experiment, in one folder of "
       "reports/, or other, by name.", rules=PICK),
    _k(part="experiment/report/*", about="One report on the experiment, by its path in "
       "reports/.", rules=PICK),
    _k(part="live/value/*", about="A run's metric a live ref in Markdown shows, by the ref as "
       "written.", rules=PICK),
    _k(part="live/figure/*", about="A figure a live ref in Markdown draws, by its ref.",
       rules=PICK),
    _k(part="report/*", about="A report's viewer: its header, page controls, the page, the "
       "figure, the note on why a deck shows as text.", rules=PICK),
    _k(part="report/block/*", about="One slide or paragraph of a deck or document's text.",
       rules=PICK),
    # Launch
    _k(part="launch/group/*", about="A group of things to launch.", rules=PICK),
    _k(part="launch/item/*", about="One thing to launch, by id (script:hello/run.py).",
       rules=PICK),
    _k(part="launch/option/*", about="One of a script's options, by flag.",
       rules=["hidden", "label", "about", "note"]),
    _k(part="launch/browse/*", about="Opens the list of tasks an option can take, by flag.",
       rules=["hidden", "label"]),
    _k(part="launch/eval/*", about="One Inspect task in that list, by task.", rules=["hidden"]),
    _k(part="launch/config", about="The training or grid config, edited in place.",
       rules=["note"]),
    _k(part="launch/where", about="Where it runs: here, Sol, a Slurm cluster, a VM or Colab.",
       rules=["note"]),
    _k(part="launch/submit/*", about="Submits it to a cluster louped.toml names, by name.",
       rules=["hidden"]),
    _k(part="launch/*", about="The picker, title, command and Launch button.", rules=PICK),
    # a job
    _k(part="job/log", about="The job's log.", rules=["note"]),
    _k(part="job/wrote", about="The runs the job wrote.", rules=["note"]),
    _k(part="job/run/*", about="One run the job wrote.", rules=PICK),
    _k(part="job/*", about="The job's title, back link, actions, facts and command.",
       rules=PICK),
]  # fmt: skip

#: A part's address: lowercase area and kind, then names with no whitespace or slash.
ADDRESS = re.compile(r"^[a-z.]+(/[^\s/]+)*$")


def kind_of(key: str) -> Kind | None:
    """The kind a layout key (or a part's address) names: same segments, a * in the kind
    standing for any name; a kind with fewer *s (more exact) first, so run/delete is run/delete
    and not run/*."""
    segs = key.split("/")
    fitting = [
        k
        for k in KINDS
        if len(want := k.part.split("/")) == len(segs)
        and all(w in ("*", s) for w, s in zip(want, segs, strict=True))
    ]
    return min(fitting, key=lambda k: k.part.count("*"), default=None)


def check(parts: dict[str, PartRule]) -> list[str]:
    """What is wrong with a layout's parts: keys that name no part, rules a part does not take."""
    errors = []
    for key, rule in parts.items():
        kind = kind_of(key) if ADDRESS.match(key) else None
        if kind is None:
            errors.append(f"parts[{key!r}]: not a part's address (ui_page lists the kinds)")
            continue
        set_ = rule.model_dump(exclude_defaults=True)
        if not set_:
            errors.append(f"parts[{key!r}]: changes nothing")
        if wrong := [r for r in set_ if r not in kind.rules]:
            takes = ", ".join(kind.rules) or "nothing (it is picked, not changed)"
            errors.append(f"parts[{key!r}]: {', '.join(wrong)} does not apply; it takes {takes}")
    return errors


class Picked(BaseModel):
    """One part a person Shift+clicked, and the page it was on."""

    id: str = Field(max_length=300, pattern=ADDRESS.pattern)
    #: The page's path and query, such as /run/?id=m-1&tab=items.
    url: str = Field(max_length=2000)
    run: str | None = Field(None, max_length=300)
    experiment: str | None = Field(None, max_length=300)
    #: Its text as shown, cut short.
    text: str = Field("", max_length=500)
    #: What it stands for: an item's record in every condition, a condition's numbers, a field's
    #: value. None for a part with nothing beyond its text.
    data: JsonValue = None


class Selection(BaseModel):
    """What a person picked in the app, in the order they picked it, for their agent."""

    parts: list[Picked] = Field(max_length=100)


class Picks(Selection):
    """The picks as the server keeps them: each new list gets the next version, and read is the
    version the agent last read (ui_selection, or `louped picks` from a prompt hook)."""

    version: int
    read: int = 0


class Read(BaseModel):
    """The agent read the picks at this version."""

    version: int = Field(ge=1)


class ShowRequest(BaseModel):
    """What an agent shows the person in the app."""

    #: A page to open first (path and query, such as /run/?id=m-1&tab=items).
    url: str | None = Field(None, max_length=2000, pattern=r"^/([^/\\].*)?$")
    #: Parts to point at by address; the first one carries the note.
    parts: list[str] = Field([], max_length=20)
    #: Markdown beside the first part (or in the corner without one), until dismissed.
    text: str | None = Field(None, max_length=4000)
    #: highlight: an outline; spotlight: everything else dimmed; pointer: a dot that travels to it.
    style: Literal["highlight", "spotlight", "pointer"] = "highlight"


class Cue(ShowRequest):
    id: int
    #: When it was queued (Unix seconds); an app opened later shows only recent ones.
    at: float
    #: pending: no app has shown it yet; shown; missing: the app has none of its parts on that
    #: page; superseded: a newer cue came before the app found its parts.
    status: Literal["pending", "shown", "missing", "superseded"] = "pending"
    missing: list[str] = []


class Cues(BaseModel):
    #: The server's clock, which a cue's at is on: an app judges a cue's age by it, not by its own.
    now: float
    cues: list[Cue]


class Seen(BaseModel):
    missing: list[str] = Field([], max_length=20)
    superseded: bool = False

"""The shapes the API returns. The UI's types are generated from these through OpenAPI."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunKind = Literal["eval", "analysis", "training"]
#: What is degenerate about a sample's reply (louped.stores.degeneracy).
Degenerate = Literal["repeat", "echo", "loop"]


class Code(BaseModel):
    """Where the code a run (or a script) ran from is: its commit, its file, and their page."""

    commit: str
    #: Whether the tree had uncommitted changes: then the commit is not exactly what ran.
    dirty: bool | None = None
    #: The file that ran, relative to the repository's root; None when it is not known.
    path: str | None = None
    #: The file (else the commit's tree) at that commit on GitHub, GitLab or Bitbucket, from
    #: the project's git remote; None for another host or no remote.
    url: str | None = None
    #: Whether a remote branch holds the commit (else the page is not there yet); None when this
    #: repository does not have the commit, so cannot say.
    pushed: bool | None = None


class RunSummary(BaseModel):
    id: str
    kind: RunKind
    name: str
    experiment: str | None
    status: str
    created: datetime | None
    model: str | None
    metrics: dict[str, float]
    samples: int | None
    #: The samples an eval will have when it ends; while it runs, samples counts those done.
    total: int | None = None
    #: Where it ran, for a run imported from another machine (sol, slurm, vm); None for here.
    host: str | None = None
    #: The launch that made it (script:<name>/train.py), for a run started with start_run from a
    #: job or an experiment script; what an experiment's gate reads.
    launch: str | None = None


class MetricPoint(BaseModel):
    step: int
    value: float
    #: When it was logged, ms since the epoch: the x of a series sampled over time (system/).
    timestamp: int | None = None


class Artifact(BaseModel):
    path: str
    size: int | None


class RunDetail(RunSummary):
    params: dict[str, str]
    tags: dict[str, str]
    history: dict[str, list[MetricPoint]]
    artifacts: list[Artifact]
    scorers: list[str]
    error: str | None
    #: An eval run's log, relative to the log directory, as Inspect View addresses it.
    log: str | None = None
    #: The code it ran: its commit, script and their page on the forge.
    code: Code | None = None


class Reading(BaseModel):
    """How a scorer read its verdict from free text."""

    #: The rule that matched ("none": no rule did, so the verdict is the scorer's default); None
    #: when the scorer does not record its rule.
    read_by: str | None = None
    #: The text the rule matched.
    matched: str | None = None


class SampleSummary(BaseModel):
    id: str
    epoch: int
    input: str
    target: str
    scores: dict[str, float | None]
    error: str | None
    #: The reply's degeneracy flags; null while the eval is still running.
    degenerate: list[Degenerate] | None = None
    #: Each reader's reading, by score: a reader is a score that records its rule (read_by) or
    #: grades C/I, on any of the run's samples.
    readings: dict[str, Reading] = Field(default_factory=dict)
    #: The run has two or more readers and they gave this sample different values.
    disagree: bool = False


class ToolCall(BaseModel):
    id: str = ""
    function: str
    arguments: str = Field(description="The arguments as indented JSON.")
    parse_error: str | None = None


class Message(BaseModel):
    role: str
    text: str
    tool_calls: list[ToolCall]
    tool_call_id: str | None = Field(None, description="On a tool result: the call it answers.")
    function: str | None = None
    error: str | None = Field(None, description="On a tool result: the tool's error.")


class Score(BaseModel):
    name: str
    value: float | None
    raw: str
    answer: str | None
    explanation: str | None
    read_by: str | None = None
    matched: str | None = None


class ModelInput(BaseModel):
    """What one model call of a sample read."""

    model: str
    #: The prompt as fed, after the chat template and with the special tokens the tokenizer adds;
    #: None when the provider does not report it (only louped/ does).
    text: str | None = None
    tokens: int | None = None
    #: The special tokens the text holds, longest first.
    special_tokens: list[str] = Field(default_factory=list)
    tokenizer: str | None = None
    #: The first 12 hex digits of the sha256 of the tokenizer's chat template.
    chat_template: str | None = None


class SampleDetail(BaseModel):
    id: str
    epoch: int
    target: str
    messages: list[Message]
    scores: list[Score]
    metadata: dict[str, str]
    error: str | None
    #: Each model call's input, in order.
    inputs: list[ModelInput] = Field(default_factory=list)


#: behavior: what models do and why; efficiency: what it costs to run them; checks: louped
#: reproducing known results, so the other two can be trusted.
Axis = Literal["behavior", "efficiency", "checks"]
#: A domain's key, as a README's front matter names it; a project's louped.toml lists its own, else
#: louped.stores.experiments.DEFAULT_DOMAINS.
Domain = str
#: active: being worked on now; parked: set up, waiting its turn; answered: the README holds a
#: result on a real model that answers the question.
Status = Literal["active", "parked", "answered"]


class Experiment(BaseModel):
    name: str
    axis: Axis
    domain: Domain
    domain_title: str
    status: Status
    question: str | None
    #: The first paragraph of the README's Result section.
    result: str | None
    runs: list[RunSummary]


#: A gate requirement's comparison.
Op = Literal["<", "<=", ">", ">=", "==", "!="]


class GateCheck(BaseModel):
    """One requirement of a gate, as written, with the value it was checked against."""

    requirement: str
    metric: str
    op: Op
    threshold: float
    #: The metric in the run the gate reads; None when there is no run or no such metric.
    actual: float | None
    passed: bool


class GateStatus(BaseModel):
    """An experiment's gate (`gate:` in its README) and whether it passes now."""

    #: The launch whose latest finished run supplies the metrics.
    launch: str
    #: That run's id; None when the launch has no finished run yet.
    run: str | None
    #: The launches refused until it passes.
    guards: list[str]
    checks: list[GateCheck]
    passed: bool
    #: Why the gate as written does not parse; the rest is then empty.
    error: str | None = None


class ExperimentDetail(Experiment):
    #: The README as Markdown, without its front matter or the Question and Result sections.
    readme: str
    #: Its gate, when the README declares one.
    gate: GateStatus | None = None


class HeatmapView(BaseModel):
    kind: Literal["heatmap"]
    title: str
    x: list[str]
    y: list[str]
    z: list[list[float]]
    x_label: str
    y_label: str
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None
    slices: dict[str, list[list[float]]] | None = None
    labels: list[list[str]] | None = None


class LineView(BaseModel):
    kind: Literal["line"]
    title: str
    x: list[float]
    series: dict[str, list[float]]
    x_label: str
    y_label: str
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None


class ScatterPoint(BaseModel):
    label: str
    x: float
    y: float


class ScatterView(BaseModel):
    kind: Literal["scatter"]
    title: str
    points: list[ScatterPoint]
    x_label: str
    y_label: str
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None


class TableView(BaseModel):
    kind: Literal["table"]
    title: str
    columns: list[str]
    rows: list[list[str | float | int | bool | None]]
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None
    links: list[list[str | None]] | None = None
    #: Links are Neuronpedia feature pages, opened embedded beside the table.
    embed: Literal["neuronpedia"] | None = None


class TokenRow(BaseModel):
    tokens: list[str]
    values: dict[str, list[float]]
    label: str | None = None


class TokensView(BaseModel):
    kind: Literal["tokens"]
    title: str
    rows: list[TokenRow]
    pairs: dict[str, list[list[float]]] | None = None
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None


class ItemSource(BaseModel):
    """Which items a figure's marks stand for, so a mark opens its item and traces to the rows,
    script and commit behind it. A plotly figure names each mark's item in its trace's `ids`; a
    vega figure in the data field `field`."""

    #: The run whose items they are; None for the run the figure is in. An experiment's own
    #: figure has no run of its own, so it names one.
    run: str | None = None
    #: The run's item folder, as the Items tab names it ("" for the top level); None when the
    #: run has one.
    folder: str | None = None
    #: For a vega figure: the data field holding each mark's item key.
    field: str | None = None


class VegaView(BaseModel):
    """Any chart as a Vega-Lite spec with its data inline: what the other kinds do not draw."""

    kind: Literal["vega"]
    title: str
    #: A Vega-Lite spec. Its data must be inline (`data.values`): the UI loads nothing else.
    spec: dict[str, Any]
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None
    #: The items its marks stand for; items.field names the data field holding their keys.
    items: ItemSource | None = None

    @model_validator(mode="after")
    def _keyed(self) -> VegaView:
        if self.items is not None and not self.items.field:
            raise ValueError("a vega figure's items name the data field holding each mark's key")
        return self


class PlotlyAnimation(BaseModel):
    """How a plotly figure moves when the app shows it. When the person's system asks for reduced
    motion, nothing moves by itself: the Play button stays."""

    model_config = ConfigDict(extra="forbid")

    #: Play the frames when the figure comes into view.
    autoplay: bool = False
    #: Play the frames again from the first after the last.
    loop: bool = False
    #: How long each frame shows, in milliseconds.
    duration_ms: int = Field(400, ge=16, le=10_000)
    #: How long the change from one frame to the next takes, in milliseconds.
    transition_ms: int = Field(0, ge=0, le=10_000)
    #: Turn the 3D camera around the z axis until the person drags the figure; frames or not.
    orbit: bool = False


#: Plotly trace types drawn in a 3D scene, which orbit turns.
_SCENE = {"scatter3d", "surface", "mesh3d", "cone", "streamtube", "volume", "isosurface"}


class PlotlyView(BaseModel):
    """A Plotly figure with its data inline: what Vega-Lite does not draw, such as points in 3D
    (scatter3d, surface) and figures that play through frames. The UI loads Plotly only when one
    is shown."""

    kind: Literal["plotly"]
    title: str
    #: Plotly traces, each with its data inline.
    data: list[dict[str, Any]] = Field(min_length=1)
    layout: dict[str, Any] = {}
    #: Frames to play through, each a {"name", "data"}: an animation with a slider.
    frames: list[dict[str, Any]] | None = None
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None
    #: The items its marks stand for, each trace naming its points' items in `ids`.
    items: ItemSource | None = None
    #: How it moves when shown: autoplay and loop play its frames, orbit turns its 3D scene.
    animation: PlotlyAnimation | None = None

    @model_validator(mode="after")
    def _inline(self) -> PlotlyView:
        if _fetches([self.data, self.layout, self.frames]):
            raise ValueError("a plotly view's data must be inline: no urls")
        traces = [*self.data, *(t for f in self.frames or [] for t in f.get("data", []))]
        if maps := sorted({t.get("type") for t in traces if _MAP.match(str(t.get("type", "")))}):
            raise ValueError(f"{', '.join(maps)} fetch map tiles or shapes from the web: "
                             "draw it with scatter or heatmap instead")  # fmt: skip
        if keys := sorted({"geo", "map", "mapbox", "images"} & self.layout.keys()):
            raise ValueError(f"layout {', '.join(keys)} fetch from the web: leave them out")
        if any("name" not in f for f in self.frames or []):
            raise ValueError("every frame needs a name: the slider steps by it")
        if self.items is not None and not any(t.get("ids") for t in traces):
            raise ValueError("a plotly figure with items names each point's item in its "
                             "trace's ids")  # fmt: skip
        if self.items is not None and self.items.field is not None:
            raise ValueError("a plotly figure's items are its traces' ids: leave field out")
        if (a := self.animation) is not None:
            if (a.autoplay or a.loop) and not self.frames:
                raise ValueError("animation autoplay and loop play frames: give the figure frames")
            if a.orbit and not any(t.get("type") in _SCENE and t.get("scene", "scene") == "scene"
                                   for t in self.data):  # fmt: skip
                raise ValueError("animation orbit turns the 3D scene: give the figure a trace "
                                 "such as scatter3d or surface in its scene")  # fmt: skip
        return self


#: Trace types that load tiles or shapes from the web whatever the figure says.
_MAP = re.compile(r"^(scattergeo|choropleth|scattermap|choroplethmap|densitymap)")


def _fetches(obj: Any) -> bool:
    """Whether any text in obj is a url a browser would fetch (http, //, data:)."""
    if isinstance(obj, str):
        return obj.startswith(("http:", "https:", "//", "data:"))
    if isinstance(obj, dict):
        return any(_fetches(v) for v in obj.values())
    return isinstance(obj, list) and any(_fetches(v) for v in obj)


#: A value a board's control or filter holds: text, a number, a yes/no, or a list of them.
Scalar = str | int | float | bool
#: A table's name or a panel's id: lowercase letters, digits, - and _.
_ID = r"^[a-z][a-z0-9_-]{0,63}$"
#: A param's name, which a Vega condition reads as a variable: lowercase letters, digits and _.
_PARAM = r"^[a-z][a-z0-9_]{0,63}$"
#: The ops a board's filter tests a row's field with.
FilterOp = Literal["==", "!=", "<", "<=", ">", ">=", "in", "contains"]


class BoardData(BaseModel):
    """One of a board's tables: its rows inline, or read from what louped already keeps."""

    model_config = ConfigDict(extra="forbid")

    rows: list[dict[str, Any]] | None = None
    #: run:<id>/<path> or experiment:<name>/<path> (a JSONL, CSV or JSON file), metrics:<run id>
    #: (its metric history: key, step, value, timestamp), or runs: / runs:<experiment> (each run
    #: with its status and metrics).
    ref: str | None = None
    #: Seconds between reads, for a run that is still going; none reads it once.
    live: int | None = Field(None, ge=2, le=3600)

    @model_validator(mode="after")
    def _one(self) -> BoardData:
        if (self.rows is None) == (self.ref is None):
            raise ValueError("a table has rows or ref, one of them")
        if self.live is not None and self.ref is None:
            raise ValueError("live reads a table again: it needs a ref")
        return self


class BoardControl(BaseModel):
    """An input over the panels: it sets the param named by its id."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_PARAM)
    kind: Literal["select", "multi", "range", "search", "toggle"]
    label: str | None = None
    about: str | None = None
    #: select and multi: their options are the distinct values of this table's field.
    data: str | None = None
    field: str | None = None
    #: select and multi: the options, when not read from a table.
    options: list[Scalar] | None = None
    #: The value before anyone sets one; none filters nothing.
    default: Scalar | list[Scalar] | None = None
    #: range: its bounds and step.
    min: float | None = None
    max: float | None = None
    step: float | None = None

    @model_validator(mode="after")
    def _shape(self) -> BoardControl:
        if (
            self.kind in ("select", "multi")
            and self.options is None
            and not (self.data and self.field)
        ):
            raise ValueError(f"control {self.id}: a {self.kind} needs options, or data and field")
        if self.kind == "range" and (self.min is None or self.max is None):
            raise ValueError(f"control {self.id}: a range needs min and max")
        return self


class BoardFilter(BaseModel):
    """Keeps the rows whose field passes op against a param (or a fixed value). A param that
    is not set keeps every row."""

    model_config = ConfigDict(extra="forbid")

    field: str
    op: FilterOp = "=="
    param: str | None = None
    value: Scalar | list[Scalar] | None = None

    @model_validator(mode="after")
    def _one(self) -> BoardFilter:
        if (self.param is None) == (self.value is None):
            raise ValueError(f"filter on {self.field}: give param or value, one of them")
        return self


class BoardSelect(BaseModel):
    """What a click on a mark, a row or a node does: param takes that row's field."""

    model_config = ConfigDict(extra="forbid")

    param: str = Field(pattern=_PARAM)
    field: str


class BoardPanel(BaseModel):
    """One panel of a board. Only the fields its kind reads are set."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID)
    kind: Literal["vega", "plotly", "table", "stat", "text", "detail", "diagram"]
    title: str | None = None
    #: How to read it, behind its ?.
    about: str | None = None
    #: The table it draws; text needs none.
    data: str | None = None
    where: list[BoardFilter] = []
    select: BoardSelect | None = None
    #: Columns it takes of the board's (default 2 of 4); the board wraps them in rows.
    span: int = Field(2, ge=1, le=4)
    height: int | None = Field(None, ge=80, le=1200)
    #: vega: a Vega-Lite spec without data; the table's rows are its data, the board's params
    #: its params (so a condition can test datum.model == model).
    spec: dict[str, Any] | None = None
    #: plotly: a trace type (scatter, scatter3d, bar, line, surface, heatmap, histogram, ...)
    #: and the fields for its axes. color splits it into one trace per value; frame plays it
    #: through the field's values, an animation; size sizes markers by a field.
    trace: str | None = None
    x: str | None = None
    y: str | None = None
    z: str | None = None
    color: str | None = None
    text: str | None = None
    size: str | None = None
    frame: str | None = None
    layout: dict[str, Any] | None = None
    #: table: its columns, in order (default all); sort by a field, highest first with desc.
    columns: list[str] | None = None
    sort: str | None = None
    desc: bool = False
    #: stat: what it computes over the field (count needs none).
    op: Literal["count", "mean", "sum", "min", "max", "distinct"] | None = None
    field: str | None = None
    format: Literal["number", "percent"] = "number"
    #: text: Markdown, with {{param}} for a param's value.
    markdown: str | None = None
    #: diagram: the data table is its nodes, edges the table of its edges; node is the field
    #: naming a node, label what it shows, source and target the edge's ends; direction LR or TB.
    edges: str | None = None
    node: str | None = None
    label: str | None = None
    source: str | None = None
    target: str | None = None
    direction: Literal["LR", "TB"] = "LR"

    @model_validator(mode="after")
    def _needs(self) -> BoardPanel:
        need: dict[str, list[str]] = {
            "vega": ["data", "spec"],
            "plotly": ["data", "trace"],
            "table": ["data"],
            "stat": ["data", "op"],
            "text": ["markdown"],
            "detail": ["data"],
            "diagram": ["data", "edges", "node", "source", "target"],
        }
        if missing := [f for f in need[self.kind] if getattr(self, f) is None]:
            raise ValueError(f"panel {self.id}: a {self.kind} panel needs {', '.join(missing)}")
        if self.kind == "stat" and self.op != "count" and self.field is None:
            raise ValueError(f"panel {self.id}: a stat's {self.op} needs a field")
        if self.spec is not None and "data" in self.spec:
            raise ValueError(f"panel {self.id}: leave data out of the spec; the board gives it")
        if _fetches([self.spec, self.layout]):
            raise ValueError(f"panel {self.id}: no urls; the board's tables are its data")
        if self.trace is not None and _MAP.match(self.trace):
            raise ValueError(f"panel {self.id}: {self.trace} fetches map tiles from the web")
        return self


class BoardView(BaseModel):
    """A dashboard: tables, controls and linked panels. A control or a click on a panel sets a
    param; every panel whose filters name it redraws. No code runs and nothing is fetched but
    louped's own data, so a board is safe to show and to commit."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["board"]
    title: str
    note: str | None = None
    about: str | None = None
    data: dict[str, BoardData] = Field(min_length=1)
    controls: list[BoardControl] = []
    panels: list[BoardPanel] = Field(min_length=1)
    #: As its own page (boards/<name>.json): the sidebar it is listed in.
    section: Literal["workspace", "behavior", "efficiency"] = "workspace"

    @model_validator(mode="after")
    def _linked(self) -> BoardView:
        problems = []
        if bad := [t for t in self.data if not re.match(_ID, t)]:
            problems.append(f"table names {bad}: lowercase letters, digits, - and _")
        ids = [p.id for p in self.panels]
        if dup := sorted({i for i in ids if ids.count(i) > 1}):
            problems.append(f"panel ids {dup} are used twice")
        params = {c.id for c in self.controls} | {p.select.param for p in self.panels if p.select}
        for c in self.controls:
            if c.data is not None and c.data not in self.data:
                problems.append(f"control {c.id} reads table {c.data}, which data does not have")
        for p in self.panels:
            for t in (p.data, p.edges):
                if t is not None and t not in self.data:
                    problems.append(f"panel {p.id} reads table {t}, which data does not have")
            for f in p.where:
                if f.param is not None and f.param not in params:
                    problems.append(f"panel {p.id} filters by param {f.param}, which no control "
                                    "or select sets")  # fmt: skip
        if problems:
            raise ValueError("; ".join(problems))
        return self


View = Annotated[
    HeatmapView
    | LineView
    | ScatterView
    | TableView
    | TokensView
    | VegaView
    | PlotlyView
    | BoardView,
    Field(discriminator="kind"),
]


class Histogram(BaseModel):
    edges: list[float]
    counts: list[int]


class FeatureDashboard(BaseModel):
    """One SAE feature over a dataset, as `louped features` logs it under features/."""

    feature: int
    hook: str
    layer: int
    density: float
    max: float
    histogram: Histogram
    #: [token, logit effect]: the unembedding rows most aligned with the decoder direction.
    promoted: list[tuple[str, float]]
    suppressed: list[tuple[str, float]]
    examples: TokensView
    neuronpedia: str | None = None
    model: str | None = None
    sae: str | None = None
    sae_id: str | None = None


class RunView(BaseModel):
    """A figure a run logged under views/, addressed by its artifact path."""

    path: str
    view: View


class TraceStep(BaseModel):
    """One link of a trace, from what was asked about down to the run it came from."""

    #: Its address, which trace takes too.
    ref: str
    what: Literal["figure", "script", "item", "run"]
    title: str
    #: For a script or a run: the commit it ran at, and whether the tree had changes then.
    commit: str | None = None
    dirty: bool | None = None
    #: For a script or a run: its code at that commit, with its page on the forge.
    code: Code | None = None
    #: For an item: its record in each file that holds it, by the file's path.
    rows: dict[str, dict[str, Any]] | None = None


class Trace(BaseModel):
    """Where a ref's evidence comes from: the figure, the script that made it, the item's rows in
    every file, and the run with its commit."""

    ref: str
    steps: list[TraceStep]


class Graph(BaseModel):
    """One circuit-tracer attribution graph."""

    slug: str
    prompt: str
    scan: str | None = None


class PairedScore(BaseModel):
    name: str
    n: int
    mean_a: float
    mean_b: float
    diff: float = Field(description="Mean of B minus A over paired samples.")
    low: float = Field(description="95% paired bootstrap interval of diff.")
    high: float
    up: int = Field(description="Samples where B scored higher.")
    down: int


class AbPair(BaseModel):
    """One pair to pick from, blind: which run gave left and which right is not said."""

    sample: str
    request: str
    left: str
    right: str
    pick: Literal["left", "right", "tie"] | None = None


class AbSession(BaseModel):
    """A blind A/B of two eval runs: their shared samples, each side placed by a seed."""

    a: str
    b: str
    pairs: list[AbPair]
    labelled: int


class AbJudge(BaseModel):
    """A judge run of the same two runs, against the person's picks."""

    run: str
    labelled: int = Field(description="Pairs both the person and the judge picked.")
    agreement: float | None = Field(description="Share of those pairs with the same pick.")
    kappa: float | None = Field(description="Cohen's kappa: agreement beyond chance.")


class AbResult(BaseModel):
    """What the person's blind picks say: how often B won, with its 95% interval."""

    a: str
    b: str
    labelled: int
    total: int
    a_wins: int
    b_wins: int
    ties: int
    b_rate: float | None = Field(description="B's win rate: B 1, tie 0.5, A 0, averaged.")
    low: float | None = Field(description="The rate's 95% bootstrap interval, low end.")
    high: float | None = Field(description="The rate's 95% bootstrap interval, high end.")
    judges: list[AbJudge]


class Agreement(BaseModel):
    """A judge run's agreement with a person's labels on its pairs."""

    labelled: int = Field(description="Pairs the person labelled.")
    total: int = Field(description="Pairs the judge judged.")
    agreement: float | None = Field(description="Share of labelled pairs with the same pick.")
    kappa: float | None = Field(description="Cohen's kappa: agreement beyond chance.")


class Comparison(BaseModel):
    a: str
    b: str
    only_a: int
    only_b: int
    scores: list[PairedScore]

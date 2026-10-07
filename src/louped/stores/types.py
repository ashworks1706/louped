"""The shapes the API returns. The UI's types are generated from these through OpenAPI."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

RunKind = Literal["eval", "analysis", "training"]
#: What is degenerate about a sample's reply (louped.stores.degeneracy).
Degenerate = Literal["repeat", "echo", "loop"]


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


class SampleSummary(BaseModel):
    id: str
    epoch: int
    input: str
    target: str
    scores: dict[str, float | None]
    error: str | None
    #: The reply's degeneracy flags; null while the eval is still running.
    degenerate: list[Degenerate] | None = None


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


class SampleDetail(BaseModel):
    id: str
    epoch: int
    target: str
    messages: list[Message]
    scores: list[Score]
    metadata: dict[str, str]
    error: str | None


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


class ExperimentDetail(Experiment):
    #: The README as Markdown, without its front matter or the Question and Result sections.
    readme: str


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


View = Annotated[
    HeatmapView | LineView | ScatterView | TableView | TokensView | VegaView | PlotlyView,
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

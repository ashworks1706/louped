"""The shapes the API returns. The UI's types are generated from these through OpenAPI."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

RunKind = Literal["eval", "analysis", "training"]


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


class VegaView(BaseModel):
    """Any chart as a Vega-Lite spec with its data inline: what the other kinds do not draw."""

    kind: Literal["vega"]
    title: str
    #: A Vega-Lite spec. Its data must be inline (`data.values`): the UI loads nothing else.
    spec: dict[str, Any]
    note: str | None = None
    #: How to read the figure, behind the ? beside its title.
    about: str | None = None


View = Annotated[
    HeatmapView | LineView | ScatterView | TableView | TokensView | VegaView,
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

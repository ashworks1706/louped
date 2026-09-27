"""The shapes the API returns. The UI's types are generated from these through OpenAPI."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

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


class MetricPoint(BaseModel):
    step: int
    value: float


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


class SampleSummary(BaseModel):
    id: str
    epoch: int
    input: str
    target: str
    scores: dict[str, float | None]
    error: str | None


class ToolCall(BaseModel):
    function: str
    arguments: str


class Message(BaseModel):
    role: str
    text: str
    tool_calls: list[ToolCall]


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


class Experiment(BaseModel):
    name: str
    question: str | None
    runs: list[RunSummary]


class HeatmapView(BaseModel):
    kind: Literal["heatmap"]
    title: str
    x: list[str]
    y: list[str]
    z: list[list[float]]
    x_label: str
    y_label: str
    note: str | None = None
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


class TableView(BaseModel):
    kind: Literal["table"]
    title: str
    columns: list[str]
    rows: list[list[str | float | int | bool | None]]
    note: str | None = None
    links: list[list[str | None]] | None = None


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


View = Annotated[HeatmapView | LineView | TableView | TokensView, Field(discriminator="kind")]


class RunView(BaseModel):
    """A figure a run logged under views/, addressed by its artifact path."""

    path: str
    view: View


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


class Comparison(BaseModel):
    a: str
    b: str
    only_a: int
    only_b: int
    scores: list[PairedScore]

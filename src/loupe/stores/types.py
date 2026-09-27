"""The shapes the API returns. The UI's types are generated from these through OpenAPI."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

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

"""A saved direction's provenance, the metadata in its safetensors header."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Direction(BaseModel):
    """Where a direction came from and what it is, stored alongside its values."""

    name: str
    model: str
    layer: int
    method: str
    norm: float
    dim: int
    created: datetime
    run: str | None = None
    notes: str | None = None

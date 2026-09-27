"""The Playground's backend: one model, loaded by `loupe serve --model`, run base or intervened.

The only route that computes rather than reads, and the only one that needs the interp extra. A
server started without --model answers that no model is loaded and imports no torch.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class PlaygroundInfo(BaseModel):
    model: str | None
    layers: int | None


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    interventions: list[dict[str, Any]] = []
    max_new_tokens: int = Field(64, ge=1, le=512)


class GenerateResponse(BaseModel):
    text: str


def router(model: str | None) -> APIRouter:
    api = APIRouter(prefix="/api/playground")
    state: dict[str, Any] = {}
    lock = threading.Lock()

    def lm():
        if model is None:
            raise HTTPException(409, "no model loaded; start with loupe serve --model <id>")
        with lock:
            if "lm" not in state:
                from loupe.models import load

                state["lm"] = load(model)
        return state["lm"]

    @api.get("")
    def info() -> PlaygroundInfo:
        if model is None:
            return PlaygroundInfo(model=None, layers=None)
        from loupe.models import n_layers

        return PlaygroundInfo(model=model, layers=n_layers(lm()))

    @api.post("/generate")
    def generate(req: GenerateRequest) -> GenerateResponse:
        from loupe.interventions import compile, parse
        from loupe.interventions import generate as run
        from loupe.models import chat

        m = lm()
        try:
            plan = compile(m, parse(req.interventions)) if req.interventions else None
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc
        with lock:  # one trace at a time on one model
            text = run(m, [chat(m, req.prompt)], plan, req.max_new_tokens)[0]
        return GenerateResponse(text=text)

    return api

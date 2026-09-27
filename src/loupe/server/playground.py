"""The Playground and Inspect backend: one model, loaded by `loupe serve --model`, run base or
intervened. Generate returns a reply; inspect returns the prompt's logit lens, attention and
projections onto saved directions as views, the same shapes a run's Figures tab draws.

The only routes that compute rather than read, and the only ones that need the interp extra. A
server started without --model answers that no model is loaded and imports no torch.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from loupe.stores.types import View


class PlaygroundInfo(BaseModel):
    model: str | None
    layers: int | None


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    interventions: list[dict[str, Any]] = []
    max_new_tokens: int = Field(64, ge=1, le=512)


class GenerateResponse(BaseModel):
    text: str


#: Attention returns layers x heads x tokens^2 weights, so inspect caps the prompt's length.
MAX_INSPECT_TOKENS = 256


class InspectRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    interventions: list[dict[str, Any]] = []
    vectors: list[str] = Field([], description="Saved directions to read, each at its own layer.")
    chat: bool = Field(True, description="Wrap the prompt in the model's chat template.")


class InspectResponse(BaseModel):
    views: list[View]


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

    def plan(m: Any, specs: list[dict[str, Any]]) -> Any:
        from loupe.interventions import compile, parse

        try:
            return compile(m, parse(specs)) if specs else None
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post("/generate")
    def generate(req: GenerateRequest) -> GenerateResponse:
        from loupe.interventions import generate as run
        from loupe.models import chat

        m = lm()
        edits = plan(m, req.interventions)
        with lock:  # one trace at a time on one model
            text = run(m, [chat(m, req.prompt)], edits, req.max_new_tokens)[0]
        return GenerateResponse(text=text)

    @api.post("/inspect")
    def inspect(req: InspectRequest) -> InspectResponse:
        from loupe.analysis import attention_patterns, logit_lens, projection
        from loupe.models import chat
        from loupe.vectors import load_vector

        m = lm()
        edits = plan(m, req.interventions)
        reads = []
        for name in req.vectors:
            try:
                vector, meta = load_vector(name)
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(400, str(exc)) from exc
            config: Any = m._model.config
            if vector.shape[-1] != config.hidden_size:
                raise HTTPException(400, f"{name} does not fit this model's residual width")
            reads.append((name, vector, meta.layer))
        prompt = chat(m, req.prompt) if req.chat else req.prompt
        if len(m.tokenizer(prompt)["input_ids"]) > MAX_INSPECT_TOKENS:
            raise HTTPException(400, f"inspect reads at most {MAX_INSPECT_TOKENS} tokens")
        with lock:
            views = [logit_lens(m, prompt, edits)[1]]
            if reads:
                views.append(projection(m, prompt, reads, edits)[1])
            views.append(attention_patterns(m, prompt, edits)[1])
        return InspectResponse.model_validate({"views": views})

    return api

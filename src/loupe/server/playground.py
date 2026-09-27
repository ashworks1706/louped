"""The Playground and Inspect backend: one model, loaded by `loupe serve --model`, run base or
intervened. Generate streams a reply as plain text, token by token; inspect returns the prompt's
logit lens, attention and projections onto saved directions as views, the same shapes a run's
Figures tab draws.

With a bank (`--bank a b`), each request names the adapters live for it. A masked diffusion model
(`--diffusion`) takes no interventions: generate sends its reply once denoised, and inspect returns
its denoising trajectory.

The only routes that compute rather than read, and the only ones that need the interp extra. A
server started without --model answers that no model is loaded and imports no torch.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import iterate_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from loupe.stores.types import View

log = logging.getLogger(__name__)


class PlaygroundInfo(BaseModel):
    model: str | None
    layers: int | None
    heads: int | None = None
    bank: list[str] = []
    diffusion: bool = False


class Ask(BaseModel):
    interventions: list[dict[str, Any]] = []
    adapters: list[str] = Field([], description="Adapters of the bank live for this request.")
    max_new_tokens: int = Field(
        64, ge=1, le=512, description="Tokens to generate; a diffusion model's reply length."
    )
    steps: int | None = Field(
        None, ge=1, le=512, description="Denoising steps; the length if unset."
    )


class GenerateRequest(Ask):
    prompt: str = Field(min_length=1, max_length=8000)


class _Stopped(Exception):
    """The client went away; the generation thread stops at its next token."""


#: Attention returns layers x heads x tokens^2 weights, so inspect caps the prompt's length.
MAX_INSPECT_TOKENS = 256
#: A trajectory is steps x reply length cells, so inspect caps both on a diffusion model.
MAX_TRAJECTORY = 128


class InspectRequest(Ask):
    prompt: str = Field(min_length=1, max_length=4000)
    vectors: list[str] = Field([], description="Saved directions to read, each at its own layer.")
    chat: bool = Field(True, description="Wrap the prompt in the model's chat template.")


class InspectResponse(BaseModel):
    views: list[View]


def router(
    model: str | None,
    bank: list[str] | None = None,
    diffusion: bool = False,
    attn: str | None = None,
) -> APIRouter:
    api = APIRouter(prefix="/api/playground")
    state: dict[str, Any] = {}
    lock = threading.Lock()  # one trace at a time on one model
    loading = threading.Lock()  # one load; never held while a trace runs

    def lm() -> Any:
        if model is None:
            raise HTTPException(409, "no model loaded; start with loupe serve --model <id>")
        with loading:
            if "lm" not in state:
                if diffusion:
                    from loupe.models.diffusion import load_diffusion

                    state["lm"] = load_diffusion(model, bank)
                else:
                    from loupe.models import load

                    state["lm"] = load(model, bank=bank, attn=attn)
        return state["lm"]

    @api.get("")
    def info() -> PlaygroundInfo:
        if model is None:
            return PlaygroundInfo(model=None, layers=None)
        m = lm()
        if diffusion:
            layers = getattr(m.model.config, "num_hidden_layers", None)
            return PlaygroundInfo(model=model, layers=layers, bank=bank or [], diffusion=True)
        from loupe.models import n_heads, n_layers

        return PlaygroundInfo(model=model, layers=n_layers(m), heads=n_heads(m), bank=bank or [])

    def live(m: Any, req: Ask) -> None:
        """Make the request's adapters live; call under the lock. A bad request raises a 400."""
        if req.adapters and not bank:
            raise HTTPException(400, "no adapter bank loaded; start with loupe serve --bank")
        if missing := set(req.adapters) - set(bank or []):
            raise HTTPException(400, f"not in the bank: {sorted(missing)}")
        if diffusion and req.interventions:
            raise HTTPException(400, "a masked diffusion model takes no interventions")
        if bank:
            from loupe.models.adapters import activate

            activate(m.model if diffusion else m._model, req.adapters)

    def plan(m: Any, req: Ask) -> Any:
        """The request's interventions compiled under its adapters; call under the lock after
        live. A bad spec raises a 400."""
        from loupe.interventions import compile, parse

        try:
            return compile(m, parse(req.interventions)) if req.interventions else None
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    def sampler(req: Ask) -> dict[str, Any]:
        """The diffusion sampler's arguments for the request; a 400 if they do not fit."""
        from loupe.models.diffusion import schedule

        args = {"length": req.max_new_tokens, "steps": req.steps or req.max_new_tokens}
        try:
            schedule(**args)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return args

    @api.post(
        "/generate",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/plain": {"schema": {"type": "string"}}}}},
    )
    def generate(req: GenerateRequest) -> StreamingResponse:
        from transformers import TextIteratorStreamer

        from loupe.interventions import generate as run
        from loupe.models import chat

        m = lm()
        args = sampler(req) if diffusion else {}
        with lock:  # a bad request is a 400 before the stream starts
            live(m, req)
            edits = plan(m, req)
        prompt = chat(m, req.prompt)
        streamer = TextIteratorStreamer(m.tokenizer, skip_prompt=True, skip_special_tokens=True)
        stop = threading.Event()

        def check(step: int, total: int) -> None:
            if stop.is_set():
                raise _Stopped

        def work() -> None:
            try:
                with lock:  # one trace at a time on one model
                    if stop.is_set():
                        return
                    live(m, req)
                    if diffusion:
                        from loupe.models.diffusion import generate as denoise

                        text = denoise(m, [prompt], check, **args)[0]
                        streamer.on_finalized_text(text, stream_end=True)
                    else:
                        run(m, [prompt], edits, req.max_new_tokens, on_step=check,
                            streamer=streamer)  # fmt: skip
            except Exception:  # nnsight wraps _Stopped, so a stop is read from the event
                if not stop.is_set():
                    log.exception("playground generation failed; the reply ends here")
                streamer.end()

        async def chunks() -> AsyncIterator[str]:
            threading.Thread(target=work, daemon=True).start()
            try:
                async for text in iterate_in_threadpool(streamer):
                    if text:
                        yield text
            finally:
                stop.set()  # a closed stream stops the generation at its next token

        return StreamingResponse(chunks(), media_type="text/plain; charset=utf-8")

    @api.post("/inspect")
    def inspect(req: InspectRequest) -> InspectResponse:
        from loupe.analysis import attention_patterns, logit_lens, projection, trajectory
        from loupe.models import chat
        from loupe.vectors import load_vector

        m = lm()
        prompt = chat(m, req.prompt) if req.chat else req.prompt
        if diffusion:
            args = sampler(req)
            if max(args.values()) > MAX_TRAJECTORY:
                raise HTTPException(
                    400, f"a trajectory reads at most {MAX_TRAJECTORY} steps and positions"
                )
            with lock:
                live(m, req)
                view = trajectory(m, prompt, **args)
            return InspectResponse.model_validate({"views": [view]})
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
        if len(m.tokenizer(prompt)["input_ids"]) > MAX_INSPECT_TOKENS:
            raise HTTPException(400, f"inspect reads at most {MAX_INSPECT_TOKENS} tokens")
        with lock:
            live(m, req)
            edits = plan(m, req)
            views = [logit_lens(m, prompt, edits)[1]]
            if reads:
                views.append(projection(m, prompt, reads, edits)[1])
            views.append(attention_patterns(m, prompt, edits)[1])
        return InspectResponse.model_validate({"views": views})

    return api

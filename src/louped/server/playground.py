"""The Playground and Inspect backend: one model, loaded from the Playground page, run base or
intervened. Generate streams a reply as plain text, token by token; inspect returns the prompt's
logit lens, attention and projections onto saved directions as views, the same shapes a run's
Figures tab draws. Patch compares a clean and a corrupt prompt layer by position (or by head);
dose sweeps a saved direction's strength and reads the next token; speed times a reply base
and changed, beside the model's footprint. Generate takes earlier turns,
so a reply can be pushed back on. Save keeps what a tool showed as a run, so a finding made here
lands beside the experiments' runs.

Loaded with a bank of adapters, each request names the adapters live for it. A masked diffusion
model takes no interventions: generate sends its reply once denoised, and inspect returns its
denoising trajectory.

The only routes that compute rather than read, and the only ones that need the interp extra. Until
a model is loaded the routes answer that none is and import no torch; the UI loads one here, or
unloads it to free the GPU, on a server that launches jobs (not one started with --expose).
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import iterate_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, JsonValue, model_validator

from louped.server.launch import require_json
from louped.stores.types import View

log = logging.getLogger(__name__)


class PlaygroundInfo(BaseModel):
    model: str | None
    layers: int | None
    heads: int | None = None
    bank: list[str] = []
    diffusion: bool = False
    #: Whether the UI may load a model here (off when the server is exposed).
    switchable: bool = False


class LoadRequest(BaseModel):
    """A model for the Playground: a Hub id, a path or a name under <home>/models; adapters to load
    beside it from <home>/adapters; whether it is a masked diffusion model; its attention kernel
    (eager, sdpa, flash_attention_2, flex_attention, a registered name, or file.py:function)."""

    model: str | None = None
    bank: list[str] = []
    diffusion: bool = False
    attn: str | None = None
    #: Run the modeling code the Hub repository ships (trust_remote_code), for an architecture
    #: transformers lacks. It executes that code on this machine.
    remote_code: bool = False

    @model_validator(mode="after")
    def _kernel_needs_causal(self) -> LoadRequest:
        if self.diffusion and self.attn:
            raise ValueError(
                "attn picks a causal model's attention kernel, not a diffusion model's"
            )
        return self


class Ask(BaseModel):
    interventions: list[dict[str, Any]] = []
    adapters: list[str] = Field([], description="Adapters of the bank live for this request.")
    max_new_tokens: int = Field(
        64, ge=1, le=512, description="Tokens to generate; a diffusion model's reply length."
    )
    steps: int | None = Field(
        None, ge=1, le=512, description="Denoising steps; the length if unset."
    )


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class GenerateRequest(Ask):
    prompt: str = Field(min_length=1, max_length=8000)
    history: list[Turn] = Field(
        [], max_length=16, description="Earlier turns, before prompt: a follow-up such as pushback."
    )


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


#: Exact patching runs one forward per layer and position (or head), so it caps the prompt.
MAX_PATCH_TOKENS = 64


class PatchRequest(BaseModel):
    """Which layer, position or head carries the difference between two prompts of one length."""

    clean: str = Field(min_length=1, max_length=4000)
    corrupt: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, description="The clean prompt's next token.")
    foil: str = Field(min_length=1, description="The corrupt prompt's next token.")
    method: Literal["attribution", "residual", "heads"] = "attribution"
    adapters: list[str] = []
    chat: bool = True


class SpeedRequest(Ask):
    """The prompt timed base and, with interventions or adapters, changed."""

    prompt: str = Field(min_length=1, max_length=8000)
    repeats: int = Field(3, ge=1, le=10)


class DoseRequest(BaseModel):
    """A saved direction swept over strengths, read at the next token."""

    prompt: str = Field(min_length=1, max_length=4000)
    vector: str
    layer: int | None = None
    alphas: list[float] = Field(min_length=2, max_length=41)
    answer: str = Field(min_length=1)
    foil: str | None = None
    adapters: list[str] = []
    chat: bool = True


Tool = Literal["reply", "inspect", "patch", "dose", "speed"]
#: The experiment a saved result goes under when the request names none: Probe's tools answer
#: what the model does, Speed what it costs.
SAVED_UNDER: dict[str, str] = {"speed": "benchmark"}
#: An experiment's name as a folder under experiments/ has it.
EXPERIMENT = r"^[a-z0-9][a-z0-9-]{0,63}$"


class SaveRequest(BaseModel):
    """What one tool showed, kept as a run: its figures, the prompt and the settings sent."""

    tool: Tool
    experiment: str | None = Field(None, pattern=EXPERIMENT)
    prompt: str = Field(min_length=1, max_length=8000)
    #: The request the tool sent (interventions, adapters, answer, alphas...), kept as JSON.
    settings: dict[str, JsonValue] = {}
    #: The intervention in words (steer refusal, strength 2, layer 3), the run's name.
    label: str = Field("", max_length=200)
    views: list[View] = Field(min_length=1, max_length=32)


class SavedResult(BaseModel):
    run: str


def _file(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "view"


def router(switchable: bool = False) -> APIRouter:
    """The Playground's routes over one model; with switchable, the UI may load it."""
    api = APIRouter(prefix="/api/playground")
    state: dict[str, Any] = {"loaded": LoadRequest()}
    lock = threading.Lock()  # one trace at a time on one model
    loading = threading.Lock()  # one load; never held while a trace runs

    def cur() -> LoadRequest:
        return state["loaded"]

    def loaded() -> tuple[Any, LoadRequest]:
        """The model and the settings it was loaded with, read together, so a load from the UI
        between two reads cannot pair one model with another's settings."""
        with loading:
            c = cur()
            if c.model is None:
                raise HTTPException(409, "no model loaded; load one on the Probe or Benchmark page")
            if "lm" not in state:
                if c.diffusion:
                    from louped.models.diffusion import load_diffusion

                    state["lm"] = load_diffusion(c.model, c.bank or None)
                else:
                    from louped.models import load

                    state["lm"] = load(c.model, bank=c.bank or None, attn=c.attn,
                                       remote_code=c.remote_code)  # fmt: skip
            return state["lm"], c

    @api.get("")
    def info() -> PlaygroundInfo:
        if cur().model is None:
            return PlaygroundInfo(model=None, layers=None, switchable=switchable)
        m, c = loaded()
        if c.diffusion:
            layers = getattr(m.model.config, "num_hidden_layers", None)
            return PlaygroundInfo(model=c.model, layers=layers, bank=c.bank, diffusion=True,
                                  switchable=switchable)  # fmt: skip
        from louped.models import n_heads, n_layers

        return PlaygroundInfo(model=c.model, layers=n_layers(m), heads=n_heads(m), bank=c.bank,
                              switchable=switchable)  # fmt: skip

    @api.post("/load", dependencies=[Depends(require_json)])
    def load_model(req: LoadRequest) -> PlaygroundInfo:
        """Replace the model (none unloads it, freeing the GPU for jobs); a bad one is a 400 and
        leaves no model loaded."""
        if not switchable:
            raise HTTPException(403, "loading a model is off on a server started with --expose")
        with lock, loading:
            state.pop("lm", None)
            state["loaded"] = req.model_copy(update={"model": req.model or None})
            import gc

            gc.collect()
            if "torch" in sys.modules and sys.modules["torch"].cuda.is_available():
                sys.modules["torch"].cuda.empty_cache()
        try:
            return info()
        except HTTPException:
            raise
        except Exception as exc:
            state["loaded"] = LoadRequest()
            raise HTTPException(400, f"could not load {req.model}: {exc}") from exc

    def live(m: Any, req: Ask, c: LoadRequest) -> None:
        """Make the request's adapters live; call under the lock. A bad request raises a 400."""
        bank, diffusion = c.bank, c.diffusion
        if req.adapters and not bank:
            raise HTTPException(400, "no adapter bank loaded; load one with the model")
        if missing := set(req.adapters) - set(bank):
            raise HTTPException(400, f"not in the bank: {sorted(missing)}")
        if diffusion and req.interventions:
            raise HTTPException(400, "a masked diffusion model takes no interventions")
        if bank:
            from louped.models.adapters import activate

            activate(m.model if diffusion else m._model, req.adapters)

    def plan(m: Any, req: Ask) -> Any:
        """The request's interventions compiled under its adapters; call under the lock after
        live. A bad spec raises a 400."""
        from louped.interventions import compile, parse

        try:
            return compile(m, parse(req.interventions)) if req.interventions else None
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    def sampler(req: Ask) -> dict[str, Any]:
        """The diffusion sampler's arguments for the request; a 400 if they do not fit."""
        from louped.models.diffusion import schedule

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

        from louped.interventions import generate as run
        from louped.models import chat

        m, c = loaded()
        diffusion = c.diffusion
        args = sampler(req) if diffusion else {}
        with lock:  # a bad request is a 400 before the stream starts
            live(m, req, c)
            edits = plan(m, req)
        prompt = chat(m, req.prompt, history=[t.model_dump() for t in req.history])
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
                    live(m, req, c)
                    if diffusion:
                        from louped.models.diffusion import generate as denoise

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
        from louped.analysis import attention_patterns, logit_lens, projection, trajectory
        from louped.models import chat
        from louped.vectors import load_vector

        m, c = loaded()
        prompt = chat(m, req.prompt) if req.chat else req.prompt
        if c.diffusion:
            args = sampler(req)
            if max(args.values()) > MAX_TRAJECTORY:
                raise HTTPException(
                    400, f"a trajectory reads at most {MAX_TRAJECTORY} steps and positions"
                )
            with lock:
                live(m, req, c)
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
            live(m, req, c)
            edits = plan(m, req)
            views = [logit_lens(m, prompt, edits)[1]]
            if reads:
                views.append(projection(m, prompt, reads, edits)[1])
            views.append(attention_patterns(m, prompt, edits)[1])
        return InspectResponse.model_validate({"views": views})

    def causal(c: LoadRequest) -> None:
        if c.diffusion:
            raise HTTPException(400, "a masked diffusion model has no next token to read")

    @api.post("/patch")
    def patch(req: PatchRequest) -> InspectResponse:
        from louped.analysis import attribution_patch, patch_heads, patch_residual
        from louped.models import chat

        m, c = loaded()
        causal(c)
        clean, corrupt = (
            (chat(m, req.clean), chat(m, req.corrupt)) if req.chat else (req.clean, req.corrupt)
        )
        cap = MAX_INSPECT_TOKENS if req.method == "attribution" else MAX_PATCH_TOKENS
        if len(m.tokenizer(clean)["input_ids"]) > cap:
            raise HTTPException(400, f"{req.method} patching reads at most {cap} tokens")
        with lock:
            live(m, Ask.model_validate({"adapters": req.adapters}), c)
            try:
                if req.method == "attribution":
                    view = attribution_patch(m, clean, corrupt, req.answer, req.foil)
                elif req.method == "residual":
                    view = patch_residual(m, clean, corrupt, req.answer, req.foil)
                else:
                    view = patch_heads(m, clean, corrupt, req.answer, req.foil)[1]
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        return InspectResponse.model_validate({"views": [view]})

    @api.post("/dose")
    def dose(req: DoseRequest) -> InspectResponse:
        from louped.analysis import dose_response
        from louped.models import chat

        m, c = loaded()
        causal(c)
        prompt = chat(m, req.prompt) if req.chat else req.prompt
        if len(m.tokenizer(prompt)["input_ids"]) > MAX_INSPECT_TOKENS:
            raise HTTPException(400, f"a dose curve reads at most {MAX_INSPECT_TOKENS} tokens")
        with lock:
            live(m, Ask.model_validate({"adapters": req.adapters}), c)
            try:
                views = dose_response(m, prompt, req.vector, req.alphas, req.answer, req.foil,
                                      req.layer)  # fmt: skip
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(400, str(exc)) from exc
        return InspectResponse.model_validate({"views": views})

    @api.post("/speed")
    def speed(req: SpeedRequest) -> InspectResponse:
        from louped.analysis import footprint, speed_view, timing
        from louped.models import chat

        m, c = loaded()
        causal(c)
        prompt = chat(m, req.prompt)
        sides = {"base": Ask.model_validate({})}
        if req.interventions or req.adapters:
            sides["changed"] = req
        timings = {}
        with lock:
            for name, side in sides.items():
                live(m, side, c)
                edits = plan(m, side)
                timings[name] = timing(m, prompt, edits, req.max_new_tokens, req.repeats)
        return InspectResponse.model_validate(
            {"views": [speed_view(timings, req.repeats), footprint(m)]}
        )

    @api.post("/save", dependencies=[Depends(require_json)])
    def save(req: SaveRequest) -> SavedResult:
        """A tool's result as an analysis run: each figure under views/, the prompt and settings
        beside them, tagged louped.source=playground."""
        import mlflow

        from louped.tracking import log_json, start_run

        if not switchable:
            raise HTTPException(403, "saving is off on a server started with --expose")
        model = cur().model
        if model is None:
            raise HTTPException(409, "no model is loaded")
        experiment = req.experiment or SAVED_UNDER.get(req.tool, "probe")
        params = {"model": model, "tool": req.tool, "intervention": req.label or "none"}
        with start_run(experiment, name=f"{req.tool} · {req.label or model}", params=params) as r:
            mlflow.set_tag("louped.source", "playground")
            mlflow.log_text(req.prompt, "prompt.txt")
            log_json(req.settings, "settings.json")
            for i, view in enumerate(req.views):
                log_json(view.model_dump(), f"views/{i:02d}-{_file(view.title)}.json")
        return SavedResult(run=f"m-{r.info.run_id}")

    return api

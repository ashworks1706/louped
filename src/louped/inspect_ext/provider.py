"""An Inspect ModelAPI over an nnsight model, with interventions given as model args.

Weights are loaded once per process and model id (and adapter bank); each provider instance only
holds its compiled plan and which of the bank's adapters are live, so a base and an ablated eval
in one process share the model. Generation is serialised with a lock because one nnsight model
runs one trace at a time; requests that arrive together for one provider are generated as one
batch (batch_size, 8 on CUDA and 1 elsewhere; 1 reproduces a run exactly, since a bf16 batch's
padding can move the last bits of a sample). A batch that runs out of GPU memory is halved and
retried, and later batches keep the smaller size. Each output records its time to first token
(ttft_s: from the start of its batch to the first token's logits). Given tools, the prompt carries
their schemas through the chat template and tool calls are parsed back with Inspect's own Hugging
Face handler, chosen by the loaded model's family, so agent tasks run under interventions too.

Adapters: bank loads named adapters beside each other, adapters makes a set of them live, phases
changes the live set along one generation. diffusion serves a masked diffusion model through
louped.models.diffusion, with the sampler's arguments ({"length": 64, "steps": 64}). revision pins
a Hub model to a commit; LLaDA and Dream from the Hub need one, since they run their own code.
attn picks the attention kernel and quant the weights' format (int8, int4; louped.models.load), so
grid conditions can differ only by either. remote_code runs the modeling code a Hub repository
ships (an architecture transformers lacks); pin revision with it.

inject ({"layer": 6, "alpha": 1.0}) takes passages a solver sent as an INJECT system message and
adds their state at that layer instead of rendering them: at every token, or with "at": "prompt" the
prompt's tokens only, or with "at": "chunks" every "chunk"-th generated token (Inject). A
conversation that ends on an assistant message is continued from it (a prefill). Specs that run the
model to compile (inject, heads with mode mean) are compiled at the first call, under the lock with
the adapters live. Each output carries its usage, counted with the model's tokenizer, and on CUDA
the call's peak memory, which louped.inspect_ext.inference scores. It also carries what the model
read (rendered_input): the prompt after the chat template, with any special tokens the tokenizer
adds around it, its length in tokens, the tokenizer and a hash of its chat template.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import torch
from inspect_ai.model import (
    ChatCompletionChoice,
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageTool,
    GenerateConfig,
    ModelAPI,
    ModelOutput,
    ModelUsage,
)
from inspect_ai.model._providers.util import HFHandler
from inspect_ai.tool import ToolChoice, ToolInfo
from inspect_ai.util._json import JSON_SCHEMA_EXTENDED_FIELDS, json_schema_dump

from louped.core import saved_model
from louped.interventions import INJECT, Heads, Inject, compile, generate, parse
from louped.interventions.specs import merge
from louped.models import load
from louped.models.adapters import activate, phase_hook
from louped.models.diffusion import Diffusion, load_diffusion
from louped.models.diffusion import generate as denoise_all
from louped.models.load import Quant

#: Tokens generated when the task's config sets no max_tokens.
DEFAULT_MAX_TOKENS = 256

_MODELS: dict[str, Any] = {}
_LOCK = threading.RLock()


@dataclass
class _Request:
    prompt: str
    max_new: int
    prefill: bool
    text: str | None = None
    peak: float | None = None
    batch: int = 1
    ttft: float | None = None
    error: BaseException | None = None


def shared_model(
    name: str,
    bank: list[str] | None = None,
    merges: list[dict[str, Any]] | None = None,
    diffusion: bool = False,
    revision: str | None = None,
    attn: str | None = None,
    quant: Quant | None = None,
    remote_code: bool = False,
) -> Any:
    """The model the provider serves under this name (with this adapter bank, attention kernel
    and weight format), loaded once per process: a LanguageModel, or a Diffusion for a masked
    diffusion model."""
    local = saved_model(name)
    key = str(local) if local else name  # a saved model's name is only unique per home
    key += json.dumps([bank or [], merges or [], diffusion, revision, attn, quant, remote_code],
                      sort_keys=True)  # fmt: skip
    with _LOCK:
        if key not in _MODELS:
            if diffusion:
                _MODELS[key] = load_diffusion(name, bank, merges, revision=revision)
            else:
                _MODELS[key] = load(name, bank=bank, merges=merges, revision=revision, attn=attn,
                                    quant=quant, remote_code=remote_code)  # fmt: skip
        return _MODELS[key]


class LoupedAPI(ModelAPI):
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig | None = None,
        interventions: Any = None,
        bank: list[str] | None = None,
        adapters: list[str] | None = None,
        merges: list[dict[str, Any]] | None = None,
        phases: list[dict[str, Any]] | None = None,
        diffusion: dict[str, Any] | None = None,
        inject: dict[str, Any] | None = None,
        revision: str | None = None,
        attn: str | None = None,
        quant: Quant | None = None,
        remote_code: bool = False,
        batch_size: int | None = None,
        **model_args: Any,
    ) -> None:
        super().__init__(model_name, base_url, api_key, [], config or GenerateConfig())
        named = set(adapters or []) | {a for p in phases or [] for a in p["adapters"]}
        bank = bank or (sorted(named) if named else None)
        if (interventions or inject or attn or quant) and diffusion is not None:
            raise ValueError(
                "interventions, attn and quant act on causal LMs, not a diffusion model"
            )
        if remote_code and diffusion is not None:
            raise ValueError("remote_code loads a causal model's own code, not a diffusion model")
        self.lm = shared_model(model_name, bank, merges, diffusion is not None, revision, attn,
                               quant, remote_code)  # fmt: skip
        self.sampler = dict(diffusion or {})
        specs = parse(interventions) if interventions else []
        self.plan = compile(self.lm, [s for s in specs if not _reads_model(s)]) if specs else {}
        self.lazy = [s for s in specs if _reads_model(s)]
        self.adapters = list(adapters or []) if bank else None
        self.phases = phases
        self.inject = inject
        self.tokenizer = self.lm.tokenizer
        self.batch_size = batch_size or (8 if torch.cuda.is_available() else 1)
        self.pending: list[_Request] = []
        self.queue = threading.Lock()

    def max_connections(self) -> int:
        return self.batch_size

    def connection_key(self) -> str:
        return f"louped:{self.model_name}"

    async def generate(
        self,
        input: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        passages = [p for m in input if m.role == "system" and m.text.startswith(INJECT)
                    for p in json.loads(m.text.removeprefix(INJECT))]  # fmt: skip
        input = [m for m in input if not (m.role == "system" and m.text.startswith(INJECT))]
        if passages and not self.inject:
            raise ValueError("passages to inject need the inject model arg: {'layer': ...}")
        prompt = self.render(input, tools)
        prefill = bool(input) and input[-1].role == "assistant"
        request = _Request(prompt, config.max_tokens or DEFAULT_MAX_TOKENS, prefill)
        if passages and self.inject:
            injected = Inject(passages=passages, **self.inject)
            await asyncio.to_thread(self._run, [request], injected)
        else:
            with self.queue:
                self.pending.append(request)
            await asyncio.to_thread(self._drain, request)
        text, peak = str(request.text), request.peak
        if not tools:
            output = ModelOutput.from_content(model=self.model_name, content=text)
        else:
            model = self.lm.model if isinstance(self.lm, Diffusion) else self.lm._model
            family = str(getattr(model.config, "model_type", self.model_name))
            message = HFHandler(self.model_name, family).parse_assistant_response(text, tools)
            stop = "tool_calls" if message.tool_calls else "stop"
            choice = ChatCompletionChoice(message=message, stop_reason=stop)
            output = ModelOutput(model=self.model_name, choices=[choice])
        n_in, n_out = await self.count_text_tokens(prompt), await self.count_text_tokens(text)
        output.usage = ModelUsage(input_tokens=n_in, output_tokens=n_out, total_tokens=n_in + n_out)
        # the batch it ran in: a bf16 batch's padding can move the last bits of a sample
        output.metadata = {"batch_size": request.batch}
        if request.ttft is not None:
            output.metadata["ttft_s"] = request.ttft
        if peak is not None:
            output.metadata["peak_cuda_mib"] = peak
        output.metadata |= self.rendered(prompt)
        return output

    def rendered(self, prompt: str) -> dict[str, Any]:
        """What the model read for this prompt: the text as it is fed, with any special tokens
        the tokenizer adds around it (a BOS), its tokens, the special tokens in it longest first,
        the tokenizer, and the first 12 hex digits of the chat template's sha256."""
        tok = self.tokenizer
        # louped.interventions.generate tokenizes with the tokenizer's additions, diffusion without
        ids = tok(prompt, add_special_tokens=not isinstance(self.lm, Diffusion))["input_ids"]
        own = tok(prompt, add_special_tokens=False)["input_ids"]
        at = next((i for i in range(len(ids) - len(own) + 1) if ids[i : i + len(own)] == own), None)
        if at is None:
            raise ValueError("the tokenizer changed the prompt's tokens when it added special ones")
        head = tok.convert_ids_to_tokens(ids[:at])
        tail = tok.convert_ids_to_tokens(ids[at + len(own) :])
        text = "".join([*head, prompt, *tail])
        specials = set(tok.all_special_tokens)
        specials |= {t.content for t in tok.added_tokens_decoder.values() if t.special}
        shown = sorted((t for t in specials if t and t in text), key=len, reverse=True)
        template = tok.chat_template
        if not isinstance(template, str):  # several named templates
            template = json.dumps(template, sort_keys=True)
        return {
            "rendered_input": text,
            "rendered_tokens": len(ids),
            "special_tokens": shown,
            "tokenizer": tok.name_or_path or self.model_name,
            "chat_template": hashlib.sha256(template.encode()).hexdigest()[:12],
        }

    def _drain(self, request: _Request) -> None:
        """Generate pending requests a batch at a time until this one is done; a batch shares the
        token budget and the prefill mode of its first request."""
        while request.text is None and request.error is None:
            with _LOCK:
                if request.text is not None or request.error is not None:
                    break
                with self.queue:
                    head = self.pending[0]
                    batch = [r for r in self.pending
                             if (r.max_new, r.prefill) == (head.max_new, head.prefill)]  # fmt: skip
                    batch = batch[: self.batch_size]
                    self.pending = [r for r in self.pending if r not in batch]
                try:
                    self._run(batch)
                except Exception as exc:  # every request in the batch fails with the real error
                    for r in batch:
                        if r.text is None:
                            r.error = exc
        if request.error is not None:
            raise request.error

    def _run(self, batch: list[_Request], inject: Inject | None = None) -> None:
        """One batch through the model with the plan, the live adapters and any phases; call
        under _LOCK, or it takes it. peak is the batch's CUDA memory high-water mark."""
        with _LOCK:
            cuda = torch.cuda.is_available()
            if cuda:
                torch.cuda.reset_peak_memory_stats()
            model = self.lm.model if isinstance(self.lm, Diffusion) else self.lm._model
            if self.adapters is not None:
                activate(model, self.adapters)
            phases = phase_hook(model, self.phases) if self.phases else None
            start, first = time.perf_counter(), []

            def hook(step: int, total: int) -> None:
                if step == 1 and not first:  # the first token's logits are out
                    first.append(time.perf_counter() - start)
                if phases is not None:
                    phases(step, total)

            prompts = [r.prompt for r in batch]
            if isinstance(self.lm, Diffusion):
                if batch[0].prefill:
                    raise ValueError("a masked diffusion model cannot continue a prefilled reply")
                # the request's token budget is the reply length, unless the sampler sets one
                sampler = {"length": batch[0].max_new, **self.sampler}
                texts = denoise_all(self.lm, prompts, phases, **sampler)
            else:
                if self.lazy:
                    self.plan = merge(self.plan, compile(self.lm, self.lazy))
                    self.lazy = []
                plan = merge(self.plan, compile(self.lm, [inject])) if inject else self.plan
                try:
                    texts = generate(self.lm, prompts, plan, batch[0].max_new,
                                     batch_size=len(batch), on_step=hook,
                                     strip=not batch[0].prefill)  # fmt: skip
                except Exception as exc:  # nnsight wraps CUDA's out of memory in its own error
                    if len(batch) == 1 or "out of memory" not in str(exc).lower():
                        raise
                    # halve the batch, now and for the requests after it
                    torch.cuda.empty_cache()
                    self.batch_size = half = len(batch) // 2
                    self._run(batch[:half], inject)
                    self._run(batch[half:], inject)
                    return
            peak = torch.cuda.max_memory_allocated() / 2**20 if cuda else None
            for r, text in zip(batch, texts, strict=True):
                r.text, r.peak, r.batch = text, peak, len(batch)
                r.ttft = first[0] if first else None

    async def count_text_tokens(self, text: str) -> int:
        """Tokens of the text by the model's own tokenizer, no special tokens added, for usage and
        for Inspect's message and token limits."""
        return len(self.tokenizer(text, add_special_tokens=False)["input_ids"])

    def render(self, input: list[ChatMessage], tools: list[ToolInfo]) -> str:
        """The conversation through the model's chat template, with the tools' JSON schemas.

        Earlier tool calls and results go in as the template's own tool_calls and tool messages,
        so the model reads them in the format it writes them. Thinking is off (Qwen3).
        """
        schemas: list[Any] = [
            json_schema_dump(t, exclude=JSON_SCHEMA_EXTENDED_FIELDS) for t in tools
        ]
        prefill = bool(input) and input[-1].role == "assistant"
        text = self.tokenizer.apply_chat_template(
            [hf_message(m) for m in input], tools=schemas or None, tokenize=False,
            add_generation_prompt=not prefill, continue_final_message=prefill,
            enable_thinking=False,
        )  # fmt: skip
        return str(text)


def _reads_model(spec: Any) -> bool:
    """Whether compiling the spec runs the model, so its result depends on the live adapters."""
    return isinstance(spec, Inject) or (isinstance(spec, Heads) and spec.mode == "mean")


def hf_message(m: ChatMessage) -> dict[str, Any]:
    """One Inspect message as a chat-template message."""
    out: dict[str, Any] = {"role": m.role, "content": m.text}
    if isinstance(m, ChatMessageAssistant) and m.tool_calls:
        out["tool_calls"] = [{"type": "function", "function": {"name": c.function,
                              "arguments": c.arguments}} for c in m.tool_calls]  # fmt: skip
    if isinstance(m, ChatMessageTool):
        out["name"] = m.function
        if m.error:
            out["content"] = f"Error: {m.error.message}"
    return out

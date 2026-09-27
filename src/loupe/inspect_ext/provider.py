"""An Inspect ModelAPI over an nnsight model, with interventions given as model args.

Weights are loaded once per process and model id (and adapter bank); each provider instance only
holds its compiled plan and which of the bank's adapters are live, so a base and an ablated eval
in one process share the model. Generation is serialised with a lock because one nnsight model
runs one trace at a time. Given tools, the prompt carries their schemas through the chat template
and tool calls are parsed back with Inspect's own Hugging Face handler, chosen by the loaded
model's family, so agent tasks run under interventions too.

Adapters: bank loads named adapters beside each other, adapters makes a set of them live, phases
changes the live set along one generation. diffusion serves a masked diffusion model through
loupe.models.diffusion, with the sampler's arguments ({"length": 64, "steps": 64}). revision pins
a Hub model to a commit; LLaDA and Dream from the Hub need one, since they run their own code.
attn picks the attention kernel (loupe.models.load), so grid conditions can differ only by it.

inject ({"layer": 6, "alpha": 1.0}) takes passages a solver sent as an INJECT system message and
adds their state at that layer instead of rendering them. A conversation that ends on an assistant
message is continued from it (a prefill). Specs that run the model to compile (inject, heads with
mode mean) are compiled at the first call, under the lock with the adapters live. Each output
carries its usage, counted with the model's tokenizer, and on CUDA the call's peak memory, which
loupe.inspect_ext.inference scores.
"""

from __future__ import annotations

import asyncio
import json
import threading
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

from loupe.core import saved_model
from loupe.interventions import INJECT, Heads, Inject, compile, generate, parse
from loupe.interventions.specs import merge
from loupe.models import load
from loupe.models.adapters import activate, phase_hook
from loupe.models.diffusion import Diffusion, load_diffusion
from loupe.models.diffusion import generate as denoise_all

_MODELS: dict[str, Any] = {}
_LOCK = threading.Lock()


def shared_model(
    name: str,
    bank: list[str] | None = None,
    merges: list[dict[str, Any]] | None = None,
    diffusion: bool = False,
    revision: str | None = None,
    attn: str | None = None,
) -> Any:
    """The model the provider serves under this name (with this adapter bank and attention
    kernel), loaded once per process: a LanguageModel, or a Diffusion for a masked diffusion
    model."""
    local = saved_model(name)
    key = str(local) if local else name  # a saved model's name is only unique per home
    key += json.dumps([bank or [], merges or [], diffusion, revision, attn], sort_keys=True)
    with _LOCK:
        if key not in _MODELS:
            if diffusion:
                _MODELS[key] = load_diffusion(name, bank, merges, revision=revision)
            else:
                _MODELS[key] = load(name, bank=bank, merges=merges, revision=revision, attn=attn)
        return _MODELS[key]


class LoupeAPI(ModelAPI):
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
        **model_args: Any,
    ) -> None:
        super().__init__(model_name, base_url, api_key, [], config or GenerateConfig())
        named = set(adapters or []) | {a for p in phases or [] for a in p["adapters"]}
        bank = bank or (sorted(named) if named else None)
        if (interventions or inject or attn) and diffusion is not None:
            raise ValueError("interventions and attn act on causal LMs, not a diffusion model")
        self.lm = shared_model(model_name, bank, merges, diffusion is not None, revision, attn)
        self.sampler = dict(diffusion or {})
        specs = parse(interventions) if interventions else []
        self.plan = compile(self.lm, [s for s in specs if not _reads_model(s)]) if specs else {}
        self.lazy = [s for s in specs if _reads_model(s)]
        self.adapters = list(adapters or []) if bank else None
        self.phases = phases
        self.inject = inject
        self.tokenizer = self.lm.tokenizer

    def max_connections(self) -> int:
        return 1

    def connection_key(self) -> str:
        return f"loupe:{self.model_name}"

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
        max_new = config.max_tokens or 256
        cuda = torch.cuda.is_available()

        def run() -> tuple[str, float | None]:
            with _LOCK:
                if cuda:
                    torch.cuda.reset_peak_memory_stats()
                model = self.lm.model if isinstance(self.lm, Diffusion) else self.lm._model
                if self.adapters is not None:
                    activate(model, self.adapters)
                hook = phase_hook(model, self.phases) if self.phases else None
                if isinstance(self.lm, Diffusion):
                    text = denoise_all(self.lm, [prompt], hook, **self.sampler)[0]
                else:
                    if self.lazy:
                        self.plan = merge(self.plan, compile(self.lm, self.lazy))
                        self.lazy = []
                    plan = self.plan
                    if passages and self.inject:
                        injected = compile(self.lm, [Inject(passages=passages, **self.inject)])
                        plan = merge(plan, injected)
                    text = generate(self.lm, [prompt], plan, max_new, on_step=hook,
                                    strip=not prefill)[0]  # fmt: skip
                return text, torch.cuda.max_memory_allocated() / 2**20 if cuda else None

        text, peak = await asyncio.to_thread(run)
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
        if peak is not None:
            output.metadata = {"peak_cuda_mib": peak}
        return output

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

"""An Inspect ModelAPI over an nnsight model, with interventions given as model args.

Weights are loaded once per process and model id (and adapter bank); each provider instance only
holds its compiled plan and which of the bank's adapters are live, so a base and an ablated eval
in one process share the model. Generation is serialised with a lock because one nnsight model
runs one trace at a time. Given tools, the prompt carries their schemas through the chat template
and tool calls are parsed back with Inspect's own Hugging Face handler, chosen by the loaded
model's family, so agent tasks run under interventions too.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from inspect_ai.model import (
    ChatCompletionChoice,
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageTool,
    GenerateConfig,
    ModelAPI,
    ModelOutput,
)
from inspect_ai.model._providers.util import HFHandler
from inspect_ai.tool import ToolChoice, ToolInfo
from inspect_ai.util._json import JSON_SCHEMA_EXTENDED_FIELDS, json_schema_dump
from nnsight import LanguageModel

from loupe.core import saved_model
from loupe.interventions import compile, generate, parse
from loupe.models import load
from loupe.models.adapters import activate

_MODELS: dict[str, LanguageModel] = {}
_LOCK = threading.Lock()


def shared_model(
    name: str, bank: list[str] | None = None, merges: list[dict[str, Any]] | None = None
) -> LanguageModel:
    """The model the provider serves under this name (with this adapter bank), loaded once per
    process."""
    local = saved_model(name)
    key = str(local) if local else name  # a saved model's name is only unique per home
    key += json.dumps([bank or [], merges or []], sort_keys=True)
    with _LOCK:
        if key not in _MODELS:
            _MODELS[key] = load(name, bank=bank, merges=merges)
        return _MODELS[key]


def release() -> None:
    """Drop every loaded model, for a grid that walks through more models than fit at once."""
    with _LOCK:
        _MODELS.clear()


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
        **model_args: Any,
    ) -> None:
        super().__init__(model_name, base_url, api_key, [], config or GenerateConfig())
        if adapters and not bank:
            bank = sorted(set(adapters))
        self.lm = shared_model(model_name, bank, merges)
        self.plan = compile(self.lm, parse(interventions)) if interventions else None
        self.adapters = list(adapters or []) if bank else None

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
        prompt = self.render(input, tools)
        max_new = config.max_tokens or 256

        def run() -> str:
            with _LOCK:
                if self.adapters is not None:
                    activate(self.lm._model, self.adapters)
                return generate(self.lm, [prompt], self.plan, max_new)[0]

        text = await asyncio.to_thread(run)
        if not tools:
            return ModelOutput.from_content(model=self.model_name, content=text)
        family = str(getattr(self.lm._model.config, "model_type", self.model_name))
        message = HFHandler(self.model_name, family).parse_assistant_response(text, tools)
        stop = "tool_calls" if message.tool_calls else "stop"
        choice = ChatCompletionChoice(message=message, stop_reason=stop)
        return ModelOutput(model=self.model_name, choices=[choice])

    async def count_text_tokens(self, text: str) -> int:
        """Tokens by the model's own tokenizer, for Inspect's message and token limits."""
        return len(self.lm.tokenizer(text)["input_ids"])

    def render(self, input: list[ChatMessage], tools: list[ToolInfo]) -> str:
        """The conversation through the model's chat template, with the tools' JSON schemas.

        Earlier tool calls and results go in as the template's own tool_calls and tool messages,
        so the model reads them in the format it writes them. Thinking is off (Qwen3).
        """
        schemas: list[Any] = [
            json_schema_dump(t, exclude=JSON_SCHEMA_EXTENDED_FIELDS) for t in tools
        ]
        text = self.lm.tokenizer.apply_chat_template(
            [hf_message(m) for m in input], tools=schemas or None, tokenize=False,
            add_generation_prompt=True, enable_thinking=False,
        )  # fmt: skip
        return str(text)


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

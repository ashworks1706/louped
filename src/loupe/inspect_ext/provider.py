"""An Inspect ModelAPI over an nnsight model, with interventions given as model args.

Weights are loaded once per process and model id; each provider instance only holds its compiled
plan, so a base and an ablated eval in one process share the model. Generation is serialised with
a lock because one nnsight model runs one trace at a time. Given tools, the prompt carries their
schemas through the chat template and tool calls are parsed back with Inspect's own Hugging Face
handler, so agent tasks run under interventions too.
"""

from __future__ import annotations

import asyncio
import copy
import threading
from typing import Any

from inspect_ai.model import (
    ChatCompletionChoice,
    ChatMessage,
    GenerateConfig,
    ModelAPI,
    ModelOutput,
)
from inspect_ai.model._providers.hf import inspect_tools_to_string, message_content_to_string
from inspect_ai.model._providers.util import HFHandler
from inspect_ai.tool import ToolChoice, ToolInfo
from inspect_ai.util._json import JSON_SCHEMA_EXTENDED_FIELDS, json_schema_dump
from nnsight import LanguageModel

from loupe.core import saved_model
from loupe.interventions import compile, generate, parse
from loupe.models import load

_MODELS: dict[str, LanguageModel] = {}
_LOCK = threading.Lock()


def shared_model(name: str) -> LanguageModel:
    """The model the provider serves under this name, loaded once per process."""
    local = saved_model(name)
    key = str(local) if local else name  # a saved model's name is only unique per home
    with _LOCK:
        if key not in _MODELS:
            _MODELS[key] = load(name)
        return _MODELS[key]


class LoupeAPI(ModelAPI):
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig | None = None,
        interventions: Any = None,
        **model_args: Any,
    ) -> None:
        super().__init__(model_name, base_url, api_key, [], config or GenerateConfig())
        self.lm = shared_model(model_name)
        self.plan = compile(self.lm, parse(interventions)) if interventions else None

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
                return generate(self.lm, [prompt], self.plan, max_new)[0]

        text = await asyncio.to_thread(run)
        if not tools:
            return ModelOutput.from_content(model=self.model_name, content=text)
        message = HFHandler(self.model_name).parse_assistant_response(text, tools)
        stop = "tool_calls" if message.tool_calls else "stop"
        choice = ChatCompletionChoice(message=message, stop_reason=stop)
        return ModelOutput(model=self.model_name, choices=[choice])

    async def count_text_tokens(self, text: str) -> int:
        """Tokens by the model's own tokenizer, for Inspect's message and token limits."""
        return len(self.lm.tokenizer(text)["input_ids"])

    def render(self, input: list[ChatMessage], tools: list[ToolInfo]) -> str:
        """The conversation through the model's chat template, with the tools' JSON schemas.

        Earlier tool calls are written into the assistant text the way Inspect's own Hugging Face
        provider does for Qwen, the format HFHandler parses back.
        """
        history = message_content_to_string(inspect_tools_to_string(copy.deepcopy(input)))
        schemas: list[Any] = [
            json_schema_dump(t, exclude=JSON_SCHEMA_EXTENDED_FIELDS) for t in tools
        ]
        messages = [m.model_dump(exclude_none=True) for m in history]
        text = self.lm.tokenizer.apply_chat_template(
            messages, tools=schemas or None, tokenize=False, add_generation_prompt=True
        )
        return str(text)

"""An Inspect ModelAPI over an nnsight model, with interventions given as model args.

Weights are loaded once per process and model id; each provider instance only holds its compiled
plan, so a base and an ablated eval in one process share the model. Generation is serialised with
a lock because one nnsight model runs one trace at a time.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from inspect_ai.model import ChatMessage, GenerateConfig, ModelAPI, ModelOutput
from inspect_ai.tool import ToolChoice, ToolInfo
from nnsight import LanguageModel

from loupe.core import saved_model
from loupe.interventions import compile, generate, parse
from loupe.models import load

_MODELS: dict[str, LanguageModel] = {}
_LOCK = threading.Lock()


def _model(name: str) -> LanguageModel:
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
        self.lm = _model(model_name)
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
        messages = [{"role": m.role, "content": m.text} for m in input]
        prompt = str(
            self.lm.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        )
        max_new = config.max_tokens or 256

        def run() -> str:
            with _LOCK:
                return generate(self.lm, [prompt], self.plan, max_new)[0]

        text = await asyncio.to_thread(run)
        return ModelOutput.from_content(model=self.model_name, content=text)

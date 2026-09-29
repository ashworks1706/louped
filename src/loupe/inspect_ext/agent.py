"""An Inspect model provider for an agent behind an OpenAI-compatible endpoint: a system that runs
its own tools and returns only its final reply.

    inspect eval cases.py --model agent/my-agent --model-base-url http://localhost:8080/v1

Such an agent is opaque to Inspect: the tools it called and the sources it used never reach the
transcript. The convention loupe reads is one extra field on the chat completion, beside
`choices`:

    "trace": {"tool_calls": [{"name": "search", "arguments": {"q": "..."}}],
              "sources": ["https://...", "doc-17"]}

The provider keeps it as the output's metadata["trace"], where loupe's case scorers read it. An
agent that sends no trace is still scored on its text. The key comes from api_key or
AGENT_API_KEY; the model id is sent as the request's model.
"""

from __future__ import annotations

import os
from typing import Any

from inspect_ai.model import (
    ChatMessage,
    GenerateConfig,
    ModelAPI,
    ModelOutput,
    ModelUsage,
)
from inspect_ai.tool import ToolChoice, ToolInfo


class AgentAPI(ModelAPI):
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig | None = None,
        timeout: float = 300.0,
        **model_args: Any,
    ) -> None:
        super().__init__(
            model_name, base_url, api_key, ["AGENT_API_KEY"], config or GenerateConfig()
        )
        if not self.base_url:
            raise ValueError("agent/ needs the agent's base_url, e.g. http://localhost:8080/v1")
        self.api_key = self.api_key or os.environ.get("AGENT_API_KEY") or "local"
        self.timeout = timeout

    def max_connections(self) -> int:
        return 4

    async def generate(
        self,
        input: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        import httpx

        if tools:
            raise ValueError("an agent/ model runs its own tools; the task must not give it any")
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.text} for m in input
                         if m.role in ("system", "user", "assistant")],
        }  # fmt: skip
        if config.max_tokens:
            body["max_tokens"] = config.max_tokens
        if config.temperature is not None:
            body["temperature"] = config.temperature
        url = f"{str(self.base_url).rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=body, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(f"{url} returned {response.status_code}: {response.text[:300]}")
        data = response.json()
        message = data["choices"][0]["message"]
        output = ModelOutput.from_content(
            model=self.model_name, content=message.get("content") or ""
        )
        usage = data.get("usage") or {}
        if usage:
            output.usage = ModelUsage(input_tokens=usage.get("prompt_tokens", 0),
                                      output_tokens=usage.get("completion_tokens", 0),
                                      total_tokens=usage.get("total_tokens", 0))  # fmt: skip
        trace = data.get("trace") or message.get("trace")
        output.metadata = {"trace": trace} if trace else {}
        return output

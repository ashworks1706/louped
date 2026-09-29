"""A TRL tool environment that replays recorded tool calls, so GRPO on tool use runs offline
against a system whose tools are live services.

    # experiments/<question>/replay.py, named in the GRPO config as environment: replay.py:Replay
    from loupe.train.replay import replay_environment
    Replay = replay_environment("recordings.json")

The recordings file holds the tools' schemas, as an OpenAI-style function list, and the calls seen:

    {"tools": [{"name": "search", "description": "Search the web.",
                "parameters": {"properties": {"query": {"type": "string",
                                                        "description": "What to look for."}},
                               "required": ["query"]}}],
     "calls": [{"tool": "search", "arguments": {"query": "library hours"}, "output": "..."}]}

A tool returns the recorded output for the same arguments; with none recorded, it says so, which
the model reads as the tool's reply. The episode's reward is 1 when the rollout called the row's
`expect_tool`, with `expect_args` in that call's arguments when the row gives it. `recordings`
builds the calls from logged model calls (loupe data's Examples).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

from loupe.data import Example

#: JSON schema types as the Python annotations TRL reads a tool's schema from.
TYPES = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list,
         "object": dict}  # fmt: skip

NO_RECORDING = "no recorded output for these arguments"


def _key(arguments: Any) -> str:
    return json.dumps(arguments, sort_keys=True)


def replay_environment(path: str | Path) -> type:
    """An environment class with one method per recorded tool, plus reset and get_reward."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    recorded: dict[tuple[str, str], str] = {
        (c["tool"], _key(c["arguments"])): str(c["output"]) for c in spec.get("calls", [])
    }
    methods: dict[str, Any] = {}
    for tool in spec["tools"]:
        methods[tool["name"]] = _method(tool, recorded)

    def reset(self, expect_tool: str | None = None, expect_args: str | None = None,
              **_: Any) -> None:  # fmt: skip
        self.calls, self.expect_tool, self.expect_args = [], expect_tool, expect_args

    def get_reward(self) -> float:
        """1 when the expected tool was called, with the expected text in its arguments."""
        for name, arguments in self.calls:
            if name == self.expect_tool and (
                not self.expect_args or self.expect_args.casefold() in arguments.casefold()
            ):
                return 1.0
        return 0.0

    return type("Replay", (), {**methods, "reset": reset, "get_reward": get_reward})


def _method(tool: dict[str, Any], recorded: dict[tuple[str, str], str]) -> Any:
    """A method named for the tool, typed and documented from its schema, so TRL builds the same
    schema the model saw; it returns the recorded output."""
    schema = tool.get("parameters") or {}
    props: dict[str, Any] = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    name = tool["name"]

    def call(self, **arguments: Any) -> str:
        self.calls.append((name, _key(arguments)))
        return recorded.get((name, _key(arguments)), NO_RECORDING)

    params = [inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    for p, info in props.items():
        kind = TYPES.get(str(info.get("type", "string")), str)
        needed = p in required
        params.append(inspect.Parameter(
            p, inspect.Parameter.KEYWORD_ONLY, default=inspect.Parameter.empty if needed else None,
            annotation=kind if needed else kind | None))  # fmt: skip
    call.__signature__ = inspect.Signature(params, return_annotation=str)  # pyright: ignore[reportFunctionMemberAccess]
    call.__annotations__ = {p.name: p.annotation for p in params[1:]} | {"return": str}
    args = "\n".join(f"    {p}: {info.get('description', p)}" for p, info in props.items())
    call.__doc__ = f"{tool.get('description', name)}\n\nArgs:\n{args}\n\nReturns:\n    The output."
    call.__name__ = call.__qualname__ = name
    return call


def recordings(examples: list[Example]) -> list[dict[str, Any]]:
    """The tool calls in logged conversations with the outputs that answered them: each assistant
    tool call paired with the tool message that carries its id."""
    out: list[dict[str, Any]] = []
    for example in examples:
        pending: dict[str, tuple[str, Any]] = {}
        for m in example.messages:
            for c in m.get("tool_calls") or []:
                fn = c.get("function") or {}
                arguments = fn.get("arguments") or "{}"
                parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                pending[str(c.get("id"))] = (str(fn.get("name")), parsed)
            if m.get("role") == "tool" and str(m.get("tool_call_id")) in pending:
                tool, arguments = pending.pop(str(m.get("tool_call_id")))
                out.append({"tool": tool, "arguments": arguments, "output": m.get("content", "")})
    return out

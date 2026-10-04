"""Inspect's entry points: louped/ (a local model under interventions) and agent/ (an agent behind
an OpenAI-compatible endpoint). Imports nothing heavy until one is asked for."""

from inspect_ai.model import ModelAPI, modelapi


@modelapi(name="louped")
def louped() -> type[ModelAPI]:
    from louped.inspect_ext.provider import LoupedAPI

    return LoupedAPI


@modelapi(name="agent")
def agent() -> type[ModelAPI]:
    from louped.inspect_ext.agent import AgentAPI

    return AgentAPI

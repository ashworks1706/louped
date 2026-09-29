"""Inspect's entry points: loupe/ (a local model under interventions) and agent/ (an agent behind
an OpenAI-compatible endpoint). Imports nothing heavy until one is asked for."""

from inspect_ai.model import ModelAPI, modelapi


@modelapi(name="loupe")
def loupe() -> type[ModelAPI]:
    from loupe.inspect_ext.provider import LoupeAPI

    return LoupeAPI


@modelapi(name="agent")
def agent() -> type[ModelAPI]:
    from loupe.inspect_ext.agent import AgentAPI

    return AgentAPI

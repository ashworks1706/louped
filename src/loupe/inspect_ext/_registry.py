"""Inspect's entry point. Imports nothing heavy until a loupe/ model is asked for."""

from inspect_ai.model import ModelAPI, modelapi


@modelapi(name="loupe")
def loupe() -> type[ModelAPI]:
    from loupe.inspect_ext.provider import LoupeAPI

    return LoupeAPI

"""Inspect's entry points: louped/ (a local model under interventions) and agent/ (an agent behind
an OpenAI-compatible endpoint), and the task louped/<name> for each benchmark louped.toml makes
from a Hub dataset ([benchmarks.<name>], louped.inspect_ext.benchmark). Imports nothing heavy
until one is asked for."""

import logging

from inspect_ai import Task, task
from inspect_ai.model import ModelAPI, modelapi

log = logging.getLogger(__name__)


@modelapi(name="louped")
def louped() -> type[ModelAPI]:
    from louped.inspect_ext.provider import LoupedAPI

    return LoupedAPI


@modelapi(name="agent")
def agent() -> type[ModelAPI]:
    from louped.inspect_ext.agent import AgentAPI

    return AgentAPI


def _register(name: str) -> None:
    def run() -> Task:
        from louped.inspect_ext.benchmark import benchmark

        return benchmark(name)

    task(name=name)(run)


def _benchmarks() -> None:
    """One task per [benchmarks.<name>] of the project's louped.toml. A file that does not read
    is said, and the providers above stay registered: Inspect drops this whole module when it
    raises."""
    from louped.core.benchmarks import benchmarks

    try:
        names = list(benchmarks())
    except ValueError as exc:
        log.warning("louped's benchmarks are not registered: %s", exc)
        return
    for name in names:
        _register(name)


_benchmarks()

"""Dose-response for steering: the next token's log-probabilities as a direction's strength moves.

One forward pass per strength, no generation, so a whole curve costs less than one reply. A
curve that rises then collapses into an unrelated top token is steering breaking the model rather
than moving the behaviour.
"""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.patching import first_token
from loupe.analysis.views import line, table
from loupe.interventions import Steer, compile, next_token_logprobs


@torch.no_grad()
def dose_response(
    lm: LanguageModel,
    prompt: str,
    vector: str,
    alphas: list[float],
    answer: str,
    foil: str | None = None,
    layer: int | None = None,
) -> list[dict[str, Any]]:
    """Steer by vector at each alpha (at layer, else the vector's own) and read the next token
    after prompt: a line of log p(answer), and log p(foil) when given, against alpha, and a table
    of the top token at each alpha."""
    targets = {answer: first_token(lm, answer)}
    if foil is not None:
        targets[foil] = first_token(lm, foil)
    series: dict[str, list[float]] = {f"log p({t!r})": [] for t in targets}
    rows: list[list[Any]] = []
    for alpha in alphas:
        plan = compile(lm, [Steer(vector=vector, alpha=alpha, layer=layer)])
        logp = next_token_logprobs(lm, [prompt], plan)[0]
        for t, i in targets.items():
            series[f"log p({t!r})"].append(round(float(logp[i]), 4))
        top = int(logp.argmax())
        rows.append([alpha, str(lm.tokenizer.decode(top)), round(float(logp[top].exp()), 4)])
    where = f"layer {layer}" if layer is not None else "its own layer"
    return [
        line(f"Steering {vector} at {where}: next-token log-probability", alphas, series,
             "alpha", "log p", note="one forward pass per strength; alpha 0 is the base model",
             about="How the answer's probability changes as the vector is added harder. A "
             "smooth monotone curve means the vector controls the behaviour."),
        table("Top next token by strength", ["alpha", "token", "p"], rows,
              about="The model's most likely next token at each strength, to spot where it "
              "stops making sense."),
    ]  # fmt: skip

"""Injecting passages' state where an engine that retrieves during generation would (piramid's
hook points): every token, the prompt only, or chunk boundaries of the reply; and loading a
model's own code only when asked."""

from typing import Any

import pytest
import torch

from loupe.interventions import Inject, compile, generate, parse
from loupe.interventions.specs import _Gated
from loupe.models.tiny import tiny


def test_prompt_and_chunk_injection_add_at_the_right_passes() -> None:
    delta = torch.ones(4)
    prompt, token = torch.zeros(1, 5, 4), torch.zeros(1, 1, 4)
    early = _Gated(delta, "prompt", chunk=1)
    assert early(prompt).sum() == 20 and early(token).sum() == 0
    chunks = _Gated(delta, "chunks", chunk=3)
    assert chunks(prompt).sum() == 0
    added = [chunks(token).sum().item() for _ in range(7)]
    assert added == [4, 0, 0, 4, 0, 0, 4]  # the first generated token, then every third
    chunks(prompt)  # a new prompt starts the count again
    assert chunks(token).sum() == 4


def test_gated_injection_runs_inside_real_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    lm = tiny()
    seen: list[int] = []
    call = _Gated.__call__

    def spy(self: _Gated, h: torch.Tensor) -> torch.Tensor:
        seen.append(h.shape[-2])
        return call(self, h)

    monkeypatch.setattr(_Gated, "__call__", spy)
    spec = Inject(passages=["the sky is blue"], layer=1, at="chunks", chunk=2)
    plan = compile(lm, [spec])
    generate(lm, ["tell me a story"], plan, max_new_tokens=4)
    # one pass over the prompt, then one per generated token after the first
    assert seen[0] > 1 and set(seen[1:]) == {1} and len(seen) >= 2
    [early] = parse({"kind": "inject", "passages": ["x"], "layer": 0, "at": "prompt"})
    assert isinstance(early, Inject) and early.at == "prompt"
    with pytest.raises(ValueError):
        Inject(passages=["x"], layer=0, at="chunks", chunk=0)


def test_remote_code_is_off_unless_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    import loupe.models.load  # noqa: F401  (the module; loupe.models exports its load function)

    load_module = sys.modules["loupe.models.load"]

    given: list[dict[str, Any]] = []

    class Spy:
        def __init__(self, model: str, **kwargs: Any) -> None:
            given.append(kwargs)
            self.tokenizer = type("T", (), {"padding_side": "right", "pad_token": "x"})()

    monkeypatch.setattr(load_module, "LanguageModel", Spy)
    load_module.load("org/custom-arch", device="cpu")
    load_module.load("org/custom-arch", device="cpu", remote_code=True, revision="abc123")
    assert "trust_remote_code" not in given[0] and given[1]["trust_remote_code"] is True


def test_the_provider_refuses_remote_code_for_a_diffusion_model() -> None:
    from loupe.inspect_ext.provider import LoupeAPI

    with pytest.raises(ValueError, match="remote_code loads a causal model"):
        LoupeAPI("x", diffusion={}, remote_code=True)

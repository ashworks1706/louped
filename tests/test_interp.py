"""Interp mechanics on a tiny random model: what is added, removed and patched is exact."""

import pytest
import torch

from loupe.analysis import last_token_resid, logit_lens, patch_residual
from loupe.interventions import Ablate, Steer, apply, compile, parse
from loupe.models import blocks, chat, n_layers
from loupe.models.tiny import tiny
from loupe.vectors import diff_in_means, list_vectors, load_vector, save_vector


@pytest.fixture(scope="module")
def lm():
    return tiny()


def hidden(lm) -> int:
    return lm._model.config.hidden_size


def test_vector_roundtrip() -> None:
    v = torch.arange(4, dtype=torch.float32)
    meta = save_vector("v1", v, model="tiny", layer=2, method="test", notes="n")
    loaded, back = load_vector("v1")
    assert torch.equal(loaded, v)
    assert back == meta
    assert [d.name for d in list_vectors()] == ["v1"]
    with pytest.raises(ValueError):
        save_vector("../escape", v, model="m", layer=0, method="x")


def test_diff_in_means() -> None:
    pos = torch.tensor([[2.0, 0.0], [4.0, 0.0]])
    neg = torch.tensor([[0.0, 1.0], [0.0, 3.0]])
    assert torch.equal(diff_in_means(pos, neg), torch.tensor([3.0, -2.0]))


def test_steer_adds_exactly_at_its_layer(lm) -> None:
    v = torch.randn(hidden(lm))
    save_vector("s", v, model="tiny", layer=1, method="random")
    prompts = [chat(lm, "write a poem"), chat(lm, "what is the answer ?")]
    with lm.trace(prompts):
        before = blocks(lm)[1].output.save()
    plan = compile(lm, [Steer(vector="s", alpha=2.0)])
    with lm.trace(prompts):
        apply(lm, plan)
        after = blocks(lm)[1].output.save()
    assert torch.allclose(after - before, (2 * v).expand_as(before), atol=1e-5)


def test_ablate_removes_the_component(lm) -> None:
    v = torch.randn(hidden(lm))
    save_vector("a", v, model="tiny", layer=0, method="random")
    unit = v / v.norm()
    last = n_layers(lm) - 1
    with lm.trace([chat(lm, "tell me a story")]):
        before = blocks(lm)[last].output.save()
    assert float((before.float() @ unit).abs().max()) > 1e-3

    plan = compile(lm, parse('{"kind": "ablate", "vector": "a"}'))
    assert sorted(plan) == [-1, *range(n_layers(lm))]  # embeddings and every block
    with lm.trace([chat(lm, "tell me a story")]):
        apply(lm, plan)
        after = blocks(lm)[last].output.save()
    assert float((after.detach().float() @ unit).abs().max()) < 1e-4


def test_out_of_range_layer_is_refused(lm) -> None:
    save_vector("r", torch.ones(hidden(lm)), model="tiny", layer=0, method="x")
    with pytest.raises(ValueError, match="out of range"):
        compile(lm, [Ablate(vector="r", layers=[99])])


def test_steer_changes_generation(lm) -> None:
    save_vector("g", torch.randn(hidden(lm)) * 50, model="tiny", layer=1, method="random")
    prompt = chat(lm, "write a poem")
    plan = compile(lm, [Steer(vector="g")])

    with lm.generate(prompt, max_new_tokens=4, do_sample=False):
        base = lm.generator.output.save()
    with lm.generate(prompt, max_new_tokens=4, do_sample=False) as tracer:
        for _ in tracer.iter[:]:
            apply(lm, plan)
        steered = lm.generator.output.save()
    assert not torch.equal(base, steered)


def test_last_token_resid_ignores_left_padding(lm) -> None:
    short, long = chat(lm, "hi"), chat(lm, "write a long poem about the blue sky please")
    alone = last_token_resid(lm, [short])
    batched = last_token_resid(lm, [short, long])
    assert batched.shape == (n_layers(lm), 2, hidden(lm))
    assert torch.allclose(alone[:, 0], batched[:, 0], atol=1e-4)


def test_logit_lens_and_patching_shapes(lm) -> None:
    view = logit_lens(lm, chat(lm, "what is the answer ?"), k=3)
    assert view["kind"] == "table" and len(view["rows"]) == n_layers(lm)

    clean, corrupt = "the cat is blue", "the dog is blue"
    grid = patch_residual(lm, clean, corrupt, answer="yes", foil="no")
    assert len(grid["z"]) == n_layers(lm)
    assert len(grid["z"][0]) == len(lm.tokenizer(clean)["input_ids"])
    # patching every position of the last layer restores the clean run exactly at the last token
    assert abs(grid["z"][-1][-1] - 1.0) < 1e-4


def test_batched_generate_matches_single(lm) -> None:
    from loupe.interventions import generate, next_token_logprobs

    prompts = [chat(lm, "write a poem"), chat(lm, "what is the answer to this question ?")]
    batch = generate(lm, prompts, max_new_tokens=3)
    single = [generate(lm, [p], max_new_tokens=3)[0] for p in prompts]
    assert batch == single
    lp = next_token_logprobs(lm, prompts)
    assert lp.shape == (2, len(lm.tokenizer))
    assert torch.allclose(lp.exp().sum(-1), torch.ones(2), atol=1e-4)


def test_inspect_provider_applies_interventions(lm) -> None:
    import asyncio

    from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model

    from loupe.core import home
    from loupe.interventions import generate

    saved = home() / "models" / "tiny-saved"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    save_vector("p", torch.randn(hidden(lm)) * 50, model="tiny-saved", layer=1, method="random")
    spec = '{"kind": "steer", "vector": "p"}'
    config = GenerateConfig(max_tokens=4)

    async def ask(interventions: str | None) -> str:
        model = get_model("loupe/tiny-saved", interventions=interventions, config=config)
        return (await model.generate([ChatMessageUser(content="write a poem")])).completion

    base, steered = asyncio.run(ask(None)), asyncio.run(ask(spec))
    prompt = chat(lm, "write a poem")
    assert base == generate(lm, [prompt], None, 4)[0]
    assert steered == generate(lm, [prompt], compile(lm, parse(spec)), 4)[0]
    assert base != steered


def test_playground_generates_base_and_intervened(lm) -> None:
    from fastapi.testclient import TestClient

    from loupe.core import home
    from loupe.server import create_app

    saved = home() / "models" / "tiny-play"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    save_vector("pv", torch.randn(hidden(lm)) * 50, model="tiny-play", layer=1, method="random")
    client = TestClient(create_app(model="tiny-play"))
    assert client.get("/api/playground").json() == {"model": "tiny-play", "layers": n_layers(lm)}
    ask = {"prompt": "write a poem", "max_new_tokens": 4}
    base = client.post("/api/playground/generate", json=ask).json()["text"]
    steer = [{"kind": "steer", "vector": "pv", "alpha": 1.0}]
    steered = client.post("/api/playground/generate", json={**ask, "interventions": steer})
    assert steered.json()["text"] != base
    bad = [{"kind": "steer", "vector": "pv", "layer": 99}]
    assert (
        client.post("/api/playground/generate", json={**ask, "interventions": bad}).status_code
        == 400
    )
    missing = [{"kind": "ablate", "vector": "nope"}]
    assert (
        client.post("/api/playground/generate", json={**ask, "interventions": missing}).status_code
        == 400
    )

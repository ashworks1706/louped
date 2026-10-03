"""Interp mechanics on a tiny random model: what is added, removed and patched is exact."""

import json
import os

import pytest
import torch

from loupe.analysis import last_token_resid, logit_lens, patch_residual
from loupe.core import home
from loupe.interventions import Ablate, Steer, apply, compile, generate, next_token_logprobs, parse
from loupe.models import blocks, chat, n_layers
from loupe.models.tiny import tiny
from loupe.stores import list_vectors
from loupe.vectors import diff_in_means, load_vector, save_vector


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
    prompt = chat(lm, "what is the answer ?")
    ids, view = logit_lens(lm, prompt)
    n = len(lm.tokenizer(prompt)["input_ids"])
    assert ids.shape == (n_layers(lm) + 1, n) and len(view["labels"][0]) == n
    # the last layer's lens is the model's own prediction
    with lm.trace(prompt):
        logits = lm.lm_head.output[0].save()
    assert torch.equal(ids[-1], logits.argmax(-1).cpu())

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


def test_inspect_provider_batches_concurrent_requests(lm) -> None:
    import asyncio

    from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model

    from loupe.interventions import generate

    saved = home() / "models" / "tiny-batched"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    asks = ["write a poem", "what is the sky", "what is the answer to this question ?"]
    model = get_model("loupe/tiny-batched", batch_size=2, config=GenerateConfig(max_tokens=4))
    calls: list[int] = []
    run = model.api._run  # pyright: ignore[reportAttributeAccessIssue]
    model.api._run = lambda batch, *a: (calls.append(len(batch)), run(batch, *a))  # pyright: ignore[reportAttributeAccessIssue]

    async def ask_all() -> list[str]:
        outs = await asyncio.gather(*[model.generate([ChatMessageUser(content=a)]) for a in asks])
        return [o.completion for o in outs]

    got = asyncio.run(ask_all())
    assert got == [generate(lm, [chat(lm, a)], None, 4)[0] for a in asks]
    assert sorted(calls) == [1, 2]  # three requests, batches of at most two


def test_inspect_provider_records_time_to_first_token(lm) -> None:
    import asyncio

    from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model

    from loupe.core import home

    saved = home() / "models" / "tiny-ttft"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    model = get_model("loupe/tiny-ttft", config=GenerateConfig(max_tokens=4))
    out = asyncio.run(model.generate([ChatMessageUser(content="write a poem")]))
    assert out.metadata is not None and 0 < out.metadata["ttft_s"] <= (out.time or 1e9)


def test_inspect_provider_halves_a_batch_that_runs_out_of_memory(lm, monkeypatch) -> None:
    import asyncio

    from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model

    from loupe.inspect_ext import provider

    saved = home() / "models" / "tiny-oom"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    sizes: list[int] = []

    def fake(model, batch, plan, max_new, batch_size=8, on_step=None, strip=True):
        sizes.append(len(batch))
        if len(batch) > 1:
            raise RuntimeError("CUDA out of memory. Tried to allocate 576.00 MiB")
        return [f"ok {batch[0][-20:]}"]

    monkeypatch.setattr(provider, "generate", fake)
    model = get_model("loupe/tiny-oom", batch_size=4, config=GenerateConfig(max_tokens=4))

    async def ask_all() -> list[str]:
        asks = [ChatMessageUser(content=f"question {i}") for i in range(4)]
        return [o.completion for o in await asyncio.gather(*[model.generate([a]) for a in asks])]

    assert all(c.startswith("ok") for c in asyncio.run(ask_all()))
    assert max(sizes) > 1 and model.api.batch_size == 1  # pyright: ignore[reportAttributeAccessIssue]


def test_inspect_provider_fails_every_request_in_a_failed_batch(lm, monkeypatch) -> None:
    import asyncio

    from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model

    from loupe.inspect_ext import provider

    saved = home() / "models" / "tiny-fail"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)

    def fake(model, batch, plan, max_new, batch_size=8, on_step=None, strip=True):
        raise ValueError("a bad prompt")

    monkeypatch.setattr(provider, "generate", fake)
    model = get_model("loupe/tiny-fail", batch_size=2, config=GenerateConfig(max_tokens=4))

    async def ask_all() -> list[BaseException | object]:
        asks = [model.generate([ChatMessageUser(content=f"q {i}")]) for i in range(3)]
        return await asyncio.gather(*asks, return_exceptions=True)

    got = asyncio.run(ask_all())
    assert all(isinstance(g, ValueError) and "a bad prompt" in str(g) for g in got)


def test_playground_streams_base_and_intervened() -> None:
    import asyncio

    from fastapi.testclient import TestClient

    from loupe.server import create_app
    from loupe.server.playground import GenerateRequest, router

    lm = tiny(train=[("write a poem", "roses are red")])  # a reply of several tokens to stream
    saved = home() / "models" / "tiny-play"
    lm._model.save_pretrained(saved)  # pyright: ignore[reportCallIssue]
    lm.tokenizer.save_pretrained(saved)
    save_vector("pv", torch.randn(hidden(lm)) * 50, model="tiny-play", layer=1, method="random")
    client = TestClient(create_app(model="tiny-play"), base_url="http://localhost")
    info = {
        "model": "tiny-play",
        "layers": n_layers(lm),
        "heads": 4,
        "bank": [],
        "diffusion": False,
        "switchable": False,
    }
    assert client.get("/api/playground").json() == info
    assert client.post("/api/playground/load", json={"model": "x"}).status_code == 403
    ask = {"prompt": "write a poem", "max_new_tokens": 4}
    res = client.post("/api/playground/generate", json=ask)
    assert res.headers["content-type"].startswith("text/plain")
    base = res.text
    assert base.strip() == generate(lm, [chat(lm, "write a poem")], max_new_tokens=4)[0] != ""
    steer = [{"kind": "steer", "vector": "pv", "alpha": 1.0}]
    steered = client.post("/api/playground/generate", json={**ask, "interventions": steer})
    assert steered.text != base

    async def chunks(response) -> list[str]:  # TestClient buffers the body; read the stream
        return [chunk async for chunk in response.body_iterator]

    (route,) = [r for r in router("tiny-play").routes if r.path.endswith("/generate")]  # pyright: ignore
    streamed = asyncio.run(chunks(route.endpoint(GenerateRequest(**ask))))  # pyright: ignore
    assert len(streamed) > 1 and "".join(streamed) == base  # one chunk per word, as they come
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


def test_the_ui_loads_and_unloads_the_playground_model() -> None:
    from fastapi.testclient import TestClient

    from loupe.server import create_app

    lm = tiny()
    lm._model.save_pretrained(home() / "models" / "tiny-load")  # pyright: ignore[reportCallIssue]
    lm.tokenizer.save_pretrained(home() / "models" / "tiny-load")
    client = TestClient(create_app(launching=True), base_url="http://localhost")
    assert client.get("/api/playground").json()["model"] is None
    info = client.post("/api/playground/load", json={"model": "tiny-load"}).json()
    assert info["model"] == "tiny-load" and info["layers"] == n_layers(lm) and info["switchable"]
    ask = {"prompt": "write a poem", "max_new_tokens": 3}
    assert client.post("/api/playground/generate", json=ask).status_code == 200
    bad = client.post("/api/playground/load", json={"model": str(home() / "no-such-model")})
    assert bad.status_code == 400 and client.get("/api/playground").json()["model"] is None
    assert client.post("/api/playground/load", json={}).json()["model"] is None


def test_closing_the_playground_stream_stops_generation(monkeypatch) -> None:
    import asyncio
    import time
    import traceback

    import loupe.interventions
    import loupe.models
    from loupe.server.playground import GenerateRequest, router

    lm = tiny(train=[("write a poem", "roses are red")])  # words to stream before the close
    lm._model.generation_config.eos_token_id = None  # pyright: ignore
    monkeypatch.setattr(loupe.models, "load", lambda *args, **kwargs: lm)
    real, ended = loupe.interventions.generate, []

    def spy(*args, **kwargs):
        try:
            out = real(*args, **kwargs)
        except BaseException as exc:
            ended.append("".join(traceback.format_exception(exc)))
            raise
        ended.append(None)
        return out

    monkeypatch.setattr(loupe.interventions, "generate", spy)
    (route,) = [r for r in router("tiny-stop").routes if r.path.endswith("/generate")]  # pyright: ignore

    async def first_then_close() -> str:
        body = route.endpoint(GenerateRequest(prompt="write a poem", max_new_tokens=200))  # pyright: ignore
        chunk = await anext(body.body_iterator)
        await body.body_iterator.aclose()
        return chunk

    async def whole(n: int) -> str:
        body = route.endpoint(GenerateRequest(prompt="write a poem", max_new_tokens=n))  # pyright: ignore
        return "".join([chunk async for chunk in body.body_iterator])

    assert asyncio.run(first_then_close())
    assert isinstance(asyncio.run(whole(3)), str)  # waits for the lock the first one held
    for _ in range(100):  # the stream can end a moment before its generation thread returns
        if len(ended) == 2:
            break
        time.sleep(0.05)
    assert "_Stopped" in str(ended[0]) and ended[1:] == [None]


def test_playground_makes_the_asked_adapters_live_and_ablates_heads(lm) -> None:
    import copy

    from fastapi.testclient import TestClient
    from peft import LoraConfig, get_peft_model

    from loupe.core import adapters_dir
    from loupe.server import create_app

    lm._model.save_pretrained(home() / "models" / "tiny-bank-play")
    lm.tokenizer.save_pretrained(home() / "models" / "tiny-bank-play")
    for seed, name in enumerate(["pa", "pb"]):
        torch.manual_seed(seed)
        cfg = LoraConfig(r=4, target_modules=["q_proj", "v_proj"], init_lora_weights=False)
        get_peft_model(copy.deepcopy(lm._model), cfg).save_pretrained(str(adapters_dir() / name))
    app = create_app(model="tiny-bank-play", bank=["pa", "pb"])
    client = TestClient(app, base_url="http://localhost")
    assert client.get("/api/playground").json()["bank"] == ["pa", "pb"]

    def lens(**ask) -> list[list[float]]:
        res = client.post("/api/playground/inspect", json={"prompt": "the sky", **ask})
        return res.json()["views"][0]["z"]

    base = lens()
    assert lens(adapters=["pa"]) != base and lens(adapters=["pa"]) != lens(adapters=["pa", "pb"])
    assert lens() == base  # the next request without adapters runs the bare base again
    heads = [{"kind": "heads", "layers": [1], "heads": [0, 2]}]
    assert lens(interventions=heads) != base
    ask = {"prompt": "the sky", "max_new_tokens": 2}
    assert client.post("/api/playground/generate", json={**ask, "adapters": ["pb"]}).is_success
    assert (
        client.post("/api/playground/generate", json={**ask, "adapters": ["x"]}).status_code == 400
    )


def test_playground_denoises_a_masked_diffusion_model() -> None:
    from fastapi.testclient import TestClient

    from loupe.models.diffusion import generate as denoise
    from loupe.models.diffusion import load_diffusion
    from loupe.models.tiny import tiny_masked
    from loupe.server import create_app

    model, tok = tiny_masked()
    model.save_pretrained(home() / "models" / "tiny-mdm-play")
    tok.save_pretrained(home() / "models" / "tiny-mdm-play")
    client = TestClient(
        create_app(model="tiny-mdm-play", diffusion=True), base_url="http://localhost"
    )
    info = client.get("/api/playground").json()
    assert info["diffusion"] and info["bank"] == [] and info["heads"] is None
    ask = {"prompt": "what is the sky", "max_new_tokens": 6, "steps": 3}
    d = load_diffusion("tiny-mdm-play")
    expected = denoise(d, [chat(d, "what is the sky")], length=6, steps=3)[0]  # pyright: ignore[reportArgumentType]
    assert client.post("/api/playground/generate", json=ask).text == expected
    (view,) = client.post("/api/playground/inspect", json=ask).json()["views"]
    assert view["kind"] == "heatmap" and len(view["z"]) == 3 and len(view["z"][0]) == 6
    steer = {**ask, "interventions": [{"kind": "steer", "vector": "pv"}]}
    assert client.post("/api/playground/generate", json=steer).status_code == 400
    assert client.post("/api/playground/inspect", json={**ask, "steps": 200}).status_code == 400


def test_attribution_patching_tracks_exact_patching(lm) -> None:
    from loupe.analysis import attribution_patch

    args = ("the cat is blue", "the dog is blue", "yes", "no")
    exact = torch.tensor(patch_residual(lm, *args)["z"])
    approx = torch.tensor(attribution_patch(lm, *args)["z"])
    assert approx.shape == exact.shape
    assert float(torch.corrcoef(torch.stack([exact.flatten(), approx.flatten()]))[0, 1]) > 0.5
    assert all(p.grad is None for p in lm._model.parameters())


def test_attention_patterns_are_causal_and_normalised(lm) -> None:
    from loupe.analysis import attention_patterns

    prompt = chat(lm, "write a poem")
    before = lm._model.config._attn_implementation
    pattern, view = attention_patterns(lm, prompt)
    n = len(lm.tokenizer(prompt)["input_ids"])
    assert pattern.shape == (n_layers(lm), lm._model.config.num_attention_heads, n, n)
    assert torch.allclose(pattern.sum(-1), torch.ones(pattern.shape[:-1]), atol=1e-5)
    assert float(pattern.triu(1).abs().max()) == 0.0  # no position attends to a later one
    assert lm._model.config._attn_implementation == before
    assert len(view["pairs"]) == pattern.shape[0] * pattern.shape[1]
    row = view["rows"][0]
    assert len(row["tokens"]) == n
    assert row["values"]["layer 0 · head 0"] == view["pairs"]["layer 0 · head 0"][-1]


def test_lens_and_attention_read_the_intervened_stream_in_order(lm) -> None:
    from loupe.analysis import attention_patterns, logit_lens
    from loupe.interventions import EMBED, steer_plan

    prompt = chat(lm, "write a poem")
    plan = steer_plan(torch.randn(hidden(lm)) * 20, EMBED)
    ids, _ = logit_lens(lm, prompt)
    steered_ids, _ = logit_lens(lm, prompt, plan)
    with lm.trace(prompt):
        apply(lm, plan)
        logits = lm.lm_head.output[0].save()
    assert torch.equal(steered_ids[-1], logits.argmax(-1).cpu())
    assert not torch.equal(ids, steered_ids)
    base, _ = attention_patterns(lm, prompt)
    steered, _ = attention_patterns(lm, prompt, plan)
    assert not torch.allclose(base[0], steered[0])  # an embedding edit reaches layer 0's attention


def test_projection_reads_the_intervened_stream(lm) -> None:
    from loupe.analysis import along, projection, resid

    v = torch.randn(hidden(lm))
    save_vector("p", v, model="tiny", layer=1, method="random")
    prompt = chat(lm, "write a poem")
    base, view = projection(lm, prompt, [("p", v, 1)])
    assert torch.allclose(base["p"], along(v)(resid(lm, prompt)[2]))
    with lm.trace(prompt):
        embedded = blocks(lm)[0].input[0].save()
    at_embed, _ = projection(lm, prompt, [("e", v, -1)])
    assert torch.allclose(at_embed["e"], along(v)(embedded.float()), atol=1e-5)
    assert view["rows"][0]["values"]["p"] == base["p"].round(decimals=4).tolist()
    plan = compile(lm, [Steer(vector="p", alpha=2.0)])
    steered, _ = projection(lm, prompt, [("p", v, 1)], plan)
    assert torch.allclose(steered["p"] - base["p"], torch.full_like(base["p"], 2 * float(v.norm())),
                          atol=1e-3)  # fmt: skip


def test_top_examples_rank_by_peak_and_drop_padding(lm) -> None:
    from loupe.analysis import along, projection, top_examples

    v = torch.randn(hidden(lm))
    prompts = [chat(lm, w) for w in ("hi", "write a long poem about the sky", "a story", "why")]
    peaks, view = top_examples(lm, prompts, 1, along(v), "top", k=2, batch_size=3)
    for prompt, peak in zip(prompts, peaks, strict=True):
        alone, _ = projection(lm, prompt, [("v", v, 1)])
        content = alone["v"][1:-1]  # the tiny template's shared <user> and <assistant> tokens
        assert abs(float(content.max()) - float(peak)) < 1e-3
    assert len(view["rows"]) == 2
    best = prompts[int(peaks.argmax())]
    assert view["rows"][0]["tokens"] == [
        lm.tokenizer.decode(t) for t in lm.tokenizer(best)["input_ids"]
    ]


def test_linear_probe_finds_a_planted_direction(lm) -> None:
    from loupe.analysis import linear_probes

    words = ["cat", "dog", "sky", "water", "fire", "cake", "song", "game", "poem", "story"]
    prompts = [f"tell me about the {w} {t}" for w in words for t in ("yes", "no")]
    labels = [int(p.endswith("yes")) for p in prompts]
    accuracy, weights, view = linear_probes(lm, prompts, labels)
    assert len(accuracy) == n_layers(lm) == weights.shape[0]
    assert accuracy[-1] == 1.0  # the last token itself is the label
    assert torch.allclose(weights.norm(dim=-1), torch.ones(n_layers(lm)))
    assert view["kind"] == "line" and view["series"]["held-out accuracy"] == accuracy


def test_feature_dashboards_match_a_direct_encode(lm) -> None:
    from sae_lens import StandardSAE, StandardSAEConfig
    from sae_lens.saes.sae import SAEMetadata

    from loupe.analysis import feature_dashboards

    cfg = StandardSAEConfig(d_in=hidden(lm), d_sae=64)
    cfg.metadata = SAEMetadata(hook_name="blocks.1.hook_resid_post")
    torch.manual_seed(0)
    sae = StandardSAE(cfg)
    texts = ["write a poem", "what is the sky", "the answer is five", "roses are red"]
    prompts = [chat(lm, t) for t in texts]
    dashes = feature_dashboards(lm, sae, prompts, top_n=3, k=2, bins=5, logits=4, batch_size=3)
    assert len(dashes) == 3 and dashes[0]["max"] >= dashes[-1]["max"]
    d = dashes[0]
    f = d["feature"]
    # the top example's peak is the feature's highest activation on that text, off the shared ends
    ids = [lm.tokenizer(p)["input_ids"] for p in prompts]
    from loupe.analysis.project import shared_ends

    head, tail = shared_ends(ids)
    per_text = []
    for p in prompts:
        with lm.trace(p):
            h = blocks(lm)[1].output.save()
        acts = sae.encode(h).detach()[0, :, f]
        per_text.append(acts[max(head, 1) : len(acts) - tail])
    assert abs(d["max"] - max(float(a.max()) for a in per_text)) < 1e-4
    fired = sum(int((a > 0).sum()) for a in per_text)
    assert abs(d["density"] - fired / sum(len(a) for a in per_text)) < 1e-6
    assert sum(d["histogram"]["counts"]) == fired and len(d["histogram"]["edges"]) == 6
    assert len(d["examples"]["rows"]) <= 2 and d["examples"]["rows"][0]["label"].startswith("peak")
    effect = lm._model.get_output_embeddings().weight @ sae.W_dec[f]
    assert [v for _, v in d["promoted"]] == pytest.approx(effect.topk(4).values.tolist(), abs=1e-4)
    assert d["suppressed"][0][1] == pytest.approx(float(effect.min()), abs=1e-4)
    assert d["neuronpedia"] is None
    assert [x["feature"] for x in feature_dashboards(lm, sae, prompts, features=[5, 9])] == [5, 9]


def test_sae_features_and_steering_a_feature(lm) -> None:
    from sae_lens import StandardSAE, StandardSAEConfig
    from sae_lens.saes.sae import SAEMetadata

    from loupe.analysis import sae_features, save_feature

    cfg = StandardSAEConfig(d_in=hidden(lm), d_sae=64)
    cfg.metadata = SAEMetadata(hook_name="blocks.1.hook_resid_post")
    torch.manual_seed(0)
    sae = StandardSAE(cfg)
    prompt = chat(lm, "write a poem")
    acts, top, over = sae_features(lm, sae, prompt, k=3)
    with lm.trace(prompt):
        resid = blocks(lm)[1].output[0].save()
    assert torch.allclose(acts, sae.encode(resid).detach(), atol=1e-6)
    assert len(top["rows"]) == acts.shape[0] and len(top["columns"]) == 5
    assert len(over["z"]) == 3 and len(over["z"][0]) == acts.shape[0]

    from loupe.analysis import feature_examples

    peak = int(acts.max(0).values.argmax())
    peaks, dash = feature_examples(lm, sae, peak, [prompt, chat(lm, "hi")], k=1)
    assert abs(float(peaks[0]) - float(acts[:, peak].max())) < 1e-4
    assert dash["rows"][0]["label"].startswith("peak")

    assert top["links"] is None
    sae.cfg.metadata.neuronpedia_id = "tiny/1-res"
    _, linked, _ = sae_features(lm, sae, prompt, k=3)
    first = next(i for i, c in enumerate(linked["rows"][0]) if isinstance(c, str) and c[0] == "#")
    feature = linked["rows"][0][first].split()[0][1:]
    assert linked["links"][0][first] == f"https://neuronpedia.org/tiny/1-res/{feature}"
    os.environ["LOUPE_NEURONPEDIA"] = "http://localhost:3100/"
    try:
        _, local, _ = sae_features(lm, sae, prompt, k=3)
    finally:
        del os.environ["LOUPE_NEURONPEDIA"]
    assert local["links"][0][first] == f"http://localhost:3100/tiny/1-res/{feature}"

    meta = save_feature(sae, 7, "feat7", model="tiny")
    assert meta.notes is not None and meta.notes.endswith("tiny/1-res/7")
    assert meta.layer == 1 and meta.method == "sae-decoder"
    with lm.trace(prompt):
        base = blocks(lm)[1].output.save()
    with lm.trace(prompt):
        apply(lm, compile(lm, [Steer(vector="feat7", alpha=3.0)]))
        steered = blocks(lm)[1].output.save()
    assert torch.allclose(steered - base, 3 * sae.W_dec[7].detach().expand_as(base), atol=1e-5)


def test_inspect_route_returns_views_under_interventions(lm) -> None:
    from fastapi.testclient import TestClient

    from loupe.server import create_app

    saved = home() / "models" / "tiny-inspect"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    save_vector("iv", torch.randn(hidden(lm)), model="tiny-inspect", layer=1, method="random")
    client = TestClient(create_app(model="tiny-inspect"), base_url="http://localhost")
    ask = {"prompt": "write a poem", "vectors": ["iv"]}
    base = client.post("/api/playground/inspect", json=ask).json()["views"]
    assert [v["kind"] for v in base] == ["heatmap", "tokens", "tokens"]
    steer = [{"kind": "steer", "vector": "iv", "alpha": 3.0}]
    steered = client.post("/api/playground/inspect", json={**ask, "interventions": steer})
    moved = steered.json()["views"][1]["rows"][0]["values"]["iv"]
    shift = [s - b for s, b in zip(moved, base[1]["rows"][0]["values"]["iv"], strict=True)]
    assert all(abs(d - shift[0]) < 1e-2 for d in shift) and shift[0] > 0
    missing = {**ask, "vectors": ["nope"]}
    assert client.post("/api/playground/inspect", json=missing).status_code == 400
    save_vector("wide", torch.randn(hidden(lm) + 1), model="tiny-inspect", layer=1, method="x")
    wrong = {**ask, "vectors": ["wide"]}
    assert client.post("/api/playground/inspect", json=wrong).status_code == 400
    long = {"prompt": "poem " * 400}
    assert client.post("/api/playground/inspect", json=long).status_code == 400


def test_patch_and_dose_routes_read_the_next_token(lm) -> None:
    from fastapi.testclient import TestClient

    from loupe.analysis import attribution_patch, dose_response, patch_residual
    from loupe.server import create_app

    saved = home() / "models" / "tiny-patch"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    save_vector("dv", torch.randn(hidden(lm)) * 10, model="tiny-patch", layer=1, method="random")
    client = TestClient(create_app(model="tiny-patch"), base_url="http://localhost")
    pair = {"clean": "the cat is blue", "corrupt": "the dog is blue", "answer": "yes",
            "foil": "no", "chat": False}  # fmt: skip
    for method, fn in (("residual", patch_residual), ("attribution", attribution_patch)):
        (view,) = client.post("/api/playground/patch", json={**pair, "method": method}).json()[
            "views"
        ]
        assert view["z"] == fn(lm, pair["clean"], pair["corrupt"], "yes", "no")["z"]
    (heads,) = client.post("/api/playground/patch", json={**pair, "method": "heads"}).json()[
        "views"
    ]
    assert len(heads["z"]) == n_layers(lm) and len(heads["z"][0]) == 4
    uneven = {**pair, "corrupt": "the big dog is blue"}
    assert client.post("/api/playground/patch", json=uneven).status_code == 400
    long = {**pair, "method": "residual", "clean": "cat " * 80, "corrupt": "dog " * 80}
    assert client.post("/api/playground/patch", json=long).status_code == 400

    ask = {"prompt": "the sky is", "vector": "dv", "alphas": [-2, 0, 2], "answer": "yes",
           "foil": "no", "chat": False}  # fmt: skip
    line, top = client.post("/api/playground/dose", json=ask).json()["views"]
    assert line["x"] == [-2, 0, 2] and len(top["rows"]) == 3
    assert line == dose_response(lm, "the sky is", "dv", [-2, 0, 2], "yes", "no")[0]
    base = next_token_logprobs(lm, ["the sky is"])[0]
    yes = lm.tokenizer.encode("yes", add_special_tokens=False)[0]
    assert abs(line["series"]["log p('yes')"][1] - float(base[yes])) < 1e-3  # alpha 0 is the base
    assert line["series"]["log p('yes')"][0] != line["series"]["log p('yes')"][2]
    missing = {**ask, "vector": "nope"}
    assert client.post("/api/playground/dose", json=missing).status_code == 400
    deep = {**ask, "layer": 99}
    assert client.post("/api/playground/dose", json=deep).status_code == 400


def test_speed_route_times_base_and_changed(lm) -> None:
    from fastapi.testclient import TestClient

    from loupe.analysis import timing
    from loupe.server import create_app

    lm2 = tiny(train=[("write a poem", "roses are red and violets are blue")])
    saved = home() / "models" / "tiny-speed"
    lm2._model.save_pretrained(saved)  # pyright: ignore[reportCallIssue]
    lm2.tokenizer.save_pretrained(saved)
    save_vector("sv", torch.randn(hidden(lm2)), model="tiny-speed", layer=1, method="random")
    t = timing(lm2, chat(lm2, "write a poem"), None, max_new_tokens=6, repeats=2)
    assert t["tokens"] > 1 and t["ttft_s"] > 0 and t["total_s"] >= t["ttft_s"]
    assert t["peak_mib"] is None  # the tiny model is on CPU, where peak memory is not recorded
    client = TestClient(create_app(model="tiny-speed"), base_url="http://localhost")
    ask = {"prompt": "write a poem", "max_new_tokens": 6, "repeats": 1}
    speed, size = client.post("/api/playground/speed", json=ask).json()["views"]
    assert [r[0] for r in speed["rows"]] == ["base"] and size["title"] == "Footprint"
    count = sum(p.numel() for p in lm2._model.parameters())
    assert dict(size["rows"])["parameters"] == f"{count / 1e6:.1f}M"
    steer = [{"kind": "steer", "vector": "sv", "alpha": 1.0}]
    changed = client.post("/api/playground/speed", json={**ask, "interventions": steer}).json()
    assert [r[0] for r in changed["views"][0]["rows"]] == ["base", "changed"]


def test_playground_continues_a_conversation(lm) -> None:
    from fastapi.testclient import TestClient

    from loupe.server import create_app

    saved = home() / "models" / "tiny-turns"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    client = TestClient(create_app(model="tiny-turns"), base_url="http://localhost")
    history = [
        {"role": "user", "content": "what is 2 + 2 ?"},
        {"role": "assistant", "content": "4"},
    ]
    ask = {"prompt": "are you sure ?", "history": history, "max_new_tokens": 4}
    got = client.post("/api/playground/generate", json=ask).text
    prompt = chat(lm, "are you sure ?", history=history)
    assert "are you sure" in prompt and prompt.index("2 + 2") < prompt.index("are you sure")
    assert got.strip() == generate(lm, [prompt], max_new_tokens=4)[0].strip()
    bad = {**ask, "history": [{"role": "system", "content": "x"}]}
    assert client.post("/api/playground/generate", json=bad).status_code == 422


def test_steering_sweep_logs_a_grid_whose_zero_cell_costs_nothing(lm) -> None:
    from inspect_ai import Task
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import generate as gen

    from loupe import stores
    from loupe.inspect_ext import refusal
    from loupe.sweep import sweep

    saved = home() / "models" / "tiny-sweep"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    save_vector("sw", torch.randn(hidden(lm)) * 30, model="tiny-sweep", layer=1, method="random")
    task = Task(dataset=[Sample(input="write a poem"), Sample(input="hi")], solver=gen(),
                scorer=refusal())  # fmt: skip
    run_id = sweep(task, "tiny-sweep", "sw", [0, 1], [0.0, 2.0], "refusal/mean",
                   neutral=["write a poem", "hi"])  # fmt: skip
    views = [v.view.model_dump() for v in stores.list_views(run_id)]
    assert [v["kind"] for v in views] == ["heatmap", "heatmap", "line", "table"]
    score, cost = views[0]["z"], views[1]["z"]
    assert len(score) == 2 and len(score[0]) == 2
    assert cost[0][0] == 0.0 and cost[1][0] == 0.0 and cost[1][1] > 0
    evals = [r for r in stores.list_runs() if r.kind == "eval"]
    assert len(evals) >= 4 and views[3]["links"][0][4].startswith("/run/?id=e-")


def test_provider_runs_a_tool_agent_and_the_transcript_keeps_the_calls(lm, monkeypatch) -> None:
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import generate as gen
    from inspect_ai.solver import use_tools
    from inspect_ai.tool import tool

    from loupe import stores
    from loupe.core import logs_dir
    from loupe.inspect_ext import provider

    @tool
    def add():
        async def execute(a: int, b: int) -> int:
            """Add two numbers.

            Args:
                a: The first.
                b: The second.
            """
            return a + b

        return execute

    saved = home() / "models" / "tiny-agent"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    replies = iter(['<tool_call>\n{"name": "add", "arguments": {"a": 2, "b": 3}}\n</tool_call>',
                    "the answer is 5"])  # fmt: skip
    prompts: list[str] = []

    def fake(model, batch, plan, max_new, batch_size=8, on_step=None, strip=True):
        prompts.extend(batch)
        return [next(replies)]

    monkeypatch.setattr(provider, "generate", fake)
    template = (
        "{% for m in messages %}<{{ m.role }}>{{ m.content }}"
        "{% for c in m.tool_calls or [] %}<tool_call>{{ c.function.name }} "
        "{{ c.function.arguments | tojson }}</tool_call>{% endfor %}{% endfor %}<assistant>"
    )
    agent_lm = provider.shared_model("tiny-agent")
    monkeypatch.setattr(agent_lm.tokenizer, "chat_template", template)
    task = Task(dataset=[Sample(input="what is 2 + 3 ?", target="5")],
                solver=[use_tools(add()), gen(tool_calls="loop")])  # fmt: skip
    [log] = eval(task, model="loupe/tiny-agent", log_dir=str(logs_dir()), display="none")
    assert log.status == "success" and len(prompts) == 2
    # the call goes back as the template's own tool_calls, then the tool's result
    assert '<tool_call>add {"a": 2, "b": 3}</tool_call><tool>5' in prompts[1]
    run = next(r for r in stores.list_runs() if r.kind == "eval")
    messages = stores.get_sample(run.id, "1").messages
    call = messages[1].tool_calls[0]
    assert (call.function, json.loads(call.arguments)) == ("add", {"a": 2, "b": 3})
    assert (messages[2].role, messages[2].function, messages[2].text) == ("tool", "add", "5")
    assert messages[2].tool_call_id == call.id and messages[3].text == "the answer is 5"


def test_transcripts_keep_tool_errors_and_parse_errors() -> None:
    from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
    from inspect_ai.tool import ToolCall, ToolCallError

    from loupe.stores.evals import _message

    call = ToolCall(id="c1", function="bash", arguments={}, parse_error="bad json")
    said = _message(ChatMessageAssistant(content="", tool_calls=[call]))
    assert (said.tool_calls[0].parse_error, said.tool_calls[0].arguments) == ("bad json", "{}")
    error = ToolCallError(type="timeout", message="took too long")
    failed = ChatMessageTool(content="", tool_call_id="c1", function="bash", error=error)
    got = _message(failed)
    assert (got.tool_call_id, got.function, got.error) == ("c1", "bash", "timeout: took too long")

"""Interp mechanics on a tiny random model: what is added, removed and patched is exact."""

import json

import pytest
import torch

from loupe.analysis import last_token_resid, logit_lens, patch_residual
from loupe.interventions import Ablate, Steer, apply, compile, parse
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

    from loupe.core import home
    from loupe.server import create_app

    saved = home() / "models" / "tiny-inspect"
    lm._model.save_pretrained(saved)
    lm.tokenizer.save_pretrained(saved)
    save_vector("iv", torch.randn(hidden(lm)), model="tiny-inspect", layer=1, method="random")
    client = TestClient(create_app(model="tiny-inspect"))
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


def test_steering_sweep_logs_a_grid_whose_zero_cell_costs_nothing(lm) -> None:
    from inspect_ai import Task
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import generate as gen

    from loupe import stores
    from loupe.core import home
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
    from loupe.core import home, logs_dir
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

    def fake(model, batch, plan, max_new):
        prompts.extend(batch)
        return [next(replies)]

    monkeypatch.setattr(provider, "generate", fake)
    task = Task(dataset=[Sample(input="what is 2 + 3 ?", target="5")],
                solver=[use_tools(add()), gen(tool_calls="loop")])  # fmt: skip
    [log] = eval(task, model="loupe/tiny-agent", log_dir=str(logs_dir()), display="none")
    assert log.status == "success" and len(prompts) == 2
    assert "5" in prompts[1]  # the tool's result went back into the second prompt
    run = next(r for r in stores.list_runs() if r.kind == "eval")
    messages = stores.get_sample(run.id, "1").messages
    call = messages[1].tool_calls[0]
    assert (call.function, json.loads(call.arguments)) == ("add", {"a": 2, "b": 3})
    assert (messages[2].role, messages[2].function, messages[2].text) == ("tool", "add", "5")
    assert messages[2].tool_call_id == call.id and messages[3].text == "the answer is 5"

"""Attention heads on a tiny random model: the Heads spec, per-head views, inference scorers."""

from __future__ import annotations

import pytest
import torch

from loupe.core import home
from loupe.interventions import Heads, apply, compile, generate, parse
from loupe.models import attention, blocks, chat, n_heads, n_layers, out_proj
from loupe.models.tiny import tiny

PROMPT = "<user> the cat is red . what is the cat ? <assistant>"


@pytest.fixture(scope="module")
def lm():
    return tiny()


@pytest.fixture(scope="module")
def trained():
    return tiny(train=[("write a poem", "the sky is blue")])


def trace(lm, plan=None) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Layer 1's attention output projection input and output, and the last logits."""
    with torch.no_grad(), lm.trace(PROMPT):
        if plan:
            apply(lm, plan)
        proj = out_proj(attention(blocks(lm)[1]))
        x, y = proj.input.save(), proj.output.save()
        logits = lm.lm_head.output[0, -1].save()
    return x, y, logits


def test_zero_heads_removes_exactly_those_heads(lm) -> None:
    [spec] = parse('{"kind": "heads", "layers": [1], "heads": [0, 2]}')
    assert isinstance(spec, Heads) and spec.mode == "zero"
    x0, _, base = trace(lm)
    x, _, logits = trace(lm, compile(lm, [spec]))
    width = x.shape[-1] // n_heads(lm)
    h, h0 = x.unflatten(-1, (n_heads(lm), width)), x0.unflatten(-1, (n_heads(lm), width))
    assert float(h[..., [0, 2], :].abs().max()) == 0.0
    assert torch.equal(h[..., [1, 3], :], h0[..., [1, 3], :])
    assert not torch.allclose(logits, base)
    every = compile(lm, [Heads(layers=[1], heads=list(range(n_heads(lm))))])
    assert float(trace(lm, every)[1].abs().max()) == 0.0  # no heads, no attention output


def test_mean_heads_fill_the_mean_over_texts(lm) -> None:
    from loupe.interventions.specs import head_means

    texts = ["the dog is blue", "write a poem about the sky"]
    spec = Heads(layers=[1], heads=[3], mode="mean", over=texts)
    x, _, _ = trace(lm, compile(lm, [spec]))
    mean = head_means(lm, texts, [1])[1].view(n_heads(lm), -1)[3]
    width = x.shape[-1] // n_heads(lm)
    assert torch.allclose(x[0, :, 3 * width :], mean.expand(x.shape[1], -1), atol=1e-6)
    with pytest.raises(ValueError, match="over"):
        Heads(layers=[1], heads=[0], mode="mean")
    with pytest.raises(ValueError, match="out of range"):
        compile(lm, [Heads(layers=[1], heads=[n_heads(lm)])])
    with pytest.raises(ValueError, match="out of range"):
        compile(lm, [Heads(layers=[n_layers(lm)], heads=[0])])


def test_heads_apply_during_generation_and_with_other_specs(trained) -> None:
    lm = trained
    prompt = chat(lm, "write a poem")
    assert generate(lm, [prompt], None, 6) == ["the sky is blue"]
    every = {"kind": "heads", "layers": [0, 1, 2, 3], "heads": [0, 1, 2, 3]}
    plan = compile(lm, parse([every, {"kind": "inject", "passages": ["the sky"], "layer": 1}]))
    assert generate(lm, [prompt], plan, 6) != generate(lm, [prompt], None, 6)


def test_mean_heads_during_cached_generation_match_a_full_recompute(trained) -> None:
    lm = trained
    prompt = chat(lm, "write a poem")
    spec = Heads(layers=[1, 2], heads=[0, 3], mode="mean", over=["the dog is blue", "a red cake"])
    plan = compile(lm, [spec])
    cached = generate(lm, [prompt], plan, 5, strip=False)[0]  # KV cache: one new token per pass
    ids = lm.tokenizer(prompt, return_tensors="pt")["input_ids"]
    for _ in range(5):
        with torch.no_grad(), lm.trace(ids):
            apply(lm, plan)
            logits = lm.lm_head.output[0, -1].save()
        ids = torch.cat([ids, logits.argmax().view(1, 1)], dim=1)
    width = len(lm.tokenizer(prompt)["input_ids"])
    full = lm.tokenizer.decode(ids[0, width:], skip_special_tokens=True)
    assert cached.strip() == full.strip() and cached != generate(lm, [prompt], None, 5)[0]


def test_attention_reads_after_head_edits(lm) -> None:
    from loupe.analysis import attention_patterns

    base, _ = attention_patterns(lm, PROMPT)
    plan = compile(lm, [Heads(layers=[0], heads=[0, 1, 2, 3])])
    ablated, _ = attention_patterns(lm, PROMPT, plan)
    assert torch.allclose(base[0], ablated[0])  # a head edit acts after its layer's weights
    assert not torch.allclose(base[1], ablated[1])


def test_attention_to_span_sums_the_span_columns(lm) -> None:
    from loupe.analysis import attention_patterns, attention_to_span

    mass, view = attention_to_span(lm, PROMPT, "the cat is red")
    pattern, _ = attention_patterns(lm, PROMPT)
    assert mass.shape == (n_layers(lm), n_heads(lm))
    assert torch.allclose(mass, pattern[:, :, -1, 1:5].sum(-1))  # tokens 1-4 after <user>
    assert view["kind"] == "heatmap" and len(view["z"]) == n_layers(lm)
    assert view["x"] == [str(j) for j in range(n_heads(lm))]
    with pytest.raises(ValueError, match="does not occur"):
        attention_to_span(lm, PROMPT, "the dog")


def test_patch_heads_grid_and_an_exact_cell(lm) -> None:
    from loupe.analysis import patch_heads

    clean, corrupt = PROMPT, PROMPT.replace("red", "blue")
    z, view = patch_heads(lm, clean, corrupt, "red", "blue")
    assert z.shape == (n_layers(lm), n_heads(lm)) and bool(torch.isfinite(z).all())
    assert view["y_label"] == "layer" and view["x_label"] == "head"
    assert view["z"] == z.round(decimals=4).tolist()
    a, b = (lm.tokenizer.encode(t, add_special_tokens=False)[0] for t in ("red", "blue"))
    last, width = n_layers(lm) - 1, lm._model.config.hidden_size // n_heads(lm)
    with torch.no_grad(), lm.trace(clean):
        head = out_proj(attention(blocks(lm)[last])).input[..., width : 2 * width].save()
        hi = lm.lm_head.output[0, -1].save()
    with torch.no_grad(), lm.trace(corrupt):
        lo = lm.lm_head.output[0, -1].save()
    with torch.no_grad(), lm.trace(corrupt):
        out_proj(attention(blocks(lm)[last])).input[..., width : 2 * width] = head
        mid = lm.lm_head.output[0, -1].save()
    d_lo, d_hi, d_mid = (float(t[a] - t[b]) for t in (lo, hi, mid))
    assert abs(float(z[last, 1]) - (d_mid - d_lo) / (d_hi - d_lo)) < 1e-4


def test_inference_scorers_read_the_provider_calls(trained) -> None:
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import generate as generate_solver

    from loupe.inspect_ext.inference import latency, peak_memory, tokens_per_second

    path = home() / "models" / "tiny-heads"
    trained._model.save_pretrained(path)
    trained.tokenizer.save_pretrained(path)
    task = Task(dataset=[Sample(input="write a poem", target="x")], solver=generate_solver(),
                scorer=[latency(), tokens_per_second(), peak_memory()])  # fmt: skip
    [log] = eval(task, model="loupe/tiny-heads", model_args={"interventions": {
        "kind": "heads", "layers": [1], "heads": [0]}}, max_tokens=5, display="none",
        log_dir=str(home() / "logs"))  # fmt: skip
    assert log.status == "success" and log.samples
    scores = log.samples[0].scores or {}
    usage = log.samples[0].output.usage
    completion = log.samples[0].output.completion
    assert (
        usage
        and usage.output_tokens
        == len(trained.tokenizer(completion, add_special_tokens=False)["input_ids"])
        > 0
    )
    assert float(scores["latency"].as_float()) > 0
    tps = usage.output_tokens / float(scores["latency"].as_float())
    assert abs(scores["tokens_per_second"].as_float() - tps) < 1e-6 * tps
    assert scores["peak_memory"].as_float() == 0.0 or torch.cuda.is_available()

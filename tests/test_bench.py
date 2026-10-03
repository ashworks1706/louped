"""Serving cost sweeps and quantized loading, on a tiny model on CPU."""

from pathlib import Path

import pytest

from loupe import stores
from loupe.bench import bench, prefill, profile, speculative, under_load
from loupe.models import save_model
from loupe.models.load import load
from loupe.models.tiny import tiny


def test_load_counts_every_requested_token_and_prefill_times_a_pass() -> None:
    lm = tiny()
    tps, seconds = under_load(lm, batch=2, new_tokens=5, repeats=1)
    assert seconds > 0 and tps == pytest.approx(10 / seconds)
    took, peak = prefill(lm, 40, repeats=1)
    assert took > 0 and peak is None  # memory is read on CUDA only


def test_bench_draws_load_and_context_per_format_and_skips_what_does_not_fit() -> None:
    lm = tiny()
    lm._model.config.max_position_embeddings = 64  # type: ignore[union-attr]
    save_model(lm, lm.tokenizer, "tiny")
    run = bench("tiny", batches=(1, 2), contexts=(16, 32, 128), new_tokens=3, repeats=1)
    views = {v.view.title: v.view for v in stores.list_views(run)}
    assert set(views) == {"Weights", "Throughput under load", "Latency under load",
                          "Prefill by context", "Speculative decoding · as saved",
                          "Where the time goes · as saved"}  # fmt: skip
    assert "profile/trace.json" in {a.path for a in stores.get_run(run).artifacts}
    load_view, prefill_view = views["Throughput under load"], views["Prefill by context"]
    assert load_view.x == [1, 2] and len(load_view.series["as saved"]) == 2  # type: ignore[union-attr]
    assert prefill_view.x == [16, 32]  # type: ignore[union-attr]
    assert prefill_view.note == "contexts over the model's 64 positions skipped"  # type: ignore[union-attr]


def test_quantized_weights_need_cuda_and_say_so() -> None:
    with pytest.raises(ValueError, match="int4 weights need CUDA"):
        load("tiny-anything", quant="int4")


def test_speculative_decoding_keeps_the_greedy_reply_and_a_draft_needs_the_same_vocabulary(
    tmp_path: Path,
) -> None:
    lm, draft = tiny(seed=0), tiny(layers=1, seed=1)
    rows = speculative(lm, new_tokens=8, repeats=1, draft=draft)
    assert [r[0] for r in rows] == ["plain", "prompt lookup", "draft model"]
    assert [r[3] for r in rows] == ["yes", "yes", "yes"] and rows[0][2] == 1.0
    draft.tokenizer.add_tokens(["<new>"])
    with pytest.raises(ValueError, match="vocabulary differs"):
        speculative(lm, new_tokens=8, repeats=1, draft=draft)


def test_a_profile_names_the_operators_and_writes_a_trace(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    ops = profile(tiny(), new_tokens=4, trace=trace)
    assert ops and all(len(row) == 4 for row in ops) and trace.stat().st_size > 0
    assert sum(row[3] for row in ops) <= 100.1

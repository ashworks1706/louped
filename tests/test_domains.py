"""The research domains on tiny offline models: the grid, adapters, decoding, retrieval."""

from __future__ import annotations

import pytest
import torch

from loupe.core import home
from loupe.models.tiny import tiny
from loupe.vectors import save_vector

ITEMS = [("what is the sky", "blue", "red"), ("what is fire", "red", "blue"),
         ("what is water", "blue", "fire")]  # fmt: skip


@pytest.fixture(scope="module")
def lm():
    return tiny()


def saved(lm, name: str) -> str:
    path = home() / "models" / name
    lm._model.save_pretrained(path)
    lm.tokenizer.save_pretrained(path)
    return name


def test_grid_pairs_conditions_against_the_baseline_per_sample(lm) -> None:
    from loupe import stores
    from loupe.grid import grid, paired, verdict
    from loupe.inspect_ext import pushback, single_turn

    name = saved(lm, "tiny-grid")
    save_vector("g", torch.randn(lm._model.config.hidden_size) * 30, model=name, layer=1,
                method="random")  # fmt: skip
    steer = {"interventions": {"kind": "steer", "vector": "g", "alpha": 4.0}}
    run_id = grid({"pushback": pushback(ITEMS), "control": single_turn(ITEMS)}, name,
                  {"base": {}, "steer": steer}, "correct_first/accuracy", seeds=[0, 1],
                  held="correct_first/accuracy")  # fmt: skip
    views = [v.view.model_dump() for v in stores.list_views(run_id)]
    assert [v["kind"] for v in views] == ["heatmap", "heatmap", "heatmap", "table"]
    assert views[0]["y"] == ["base", "steer"] and views[0]["x"] == ["pushback", "control"]
    assert views[1]["z"][0] == [0.0, 0.0]  # the baseline against itself
    rows = views[3]["rows"]
    assert rows[0][4] == "baseline" and rows[2][4].split(", ")[1] in ("held", "broke")
    assert len([r for r in stores.list_runs() if r.kind == "eval"]) == 8  # 2 x 2 x 2 seeds

    a = {("1", 1, 0): 0.0, ("2", 1, 0): 0.0, ("3", 1, 0): 0.0}
    b = {("1", 1, 0): 1.0, ("2", 1, 0): 1.0, ("3", 1, 0): 1.0}
    moved = paired(a, b)
    assert moved == (1.0, 1.0, 1.0) and verdict(moved, paired(a, a)) == "moved, held"
    assert verdict(paired(a, a), paired(b, a)) == "same, broke"


def lora(lm, name: str, seed: int) -> str:
    """A LoRA adapter on the tiny model with random non-zero deltas, saved under adapters."""
    import copy

    from peft import LoraConfig, get_peft_model

    from loupe.core import adapters_dir

    torch.manual_seed(seed)
    cfg = LoraConfig(r=4, target_modules=["q_proj", "v_proj"], init_lora_weights=False)
    peft = get_peft_model(copy.deepcopy(lm._model), cfg)
    peft.save_pretrained(str(adapters_dir() / name))
    return name


def test_adapter_bank_switches_subsets_without_reloading(lm) -> None:
    from loupe.models import load
    from loupe.models.adapters import activate, overlap, subsets

    name = saved(lm, "tiny-bank")
    a, b = lora(lm, "a", 1), lora(lm, "b", 2)
    banked = load(name, bank=[a, b], merges=[{"names": [a, b], "method": "linear"}])
    ids = banked.tokenizer("what is the sky", return_tensors="pt")["input_ids"]

    def logits(names: list[str]) -> torch.Tensor:
        activate(banked._model, names)
        with torch.no_grad():
            return banked._model(ids).logits

    bare = logits([])
    torch.testing.assert_close(bare, lm._model(ids).logits.detach())  # none is the base
    live = {k: logits(v) for k, v in subsets([a, b]).items() if v}
    assert not torch.allclose(live["a"], bare) and not torch.allclose(live["a"], live["b"])
    assert not torch.allclose(live["a+b"], live["a"])
    assert not torch.allclose(logits(["linear:a+b"]), bare)
    with pytest.raises(KeyError):
        activate(banked._model, ["c"])
    pairs, sites, grid_ = overlap(banked._model)
    assert pairs == ["a · b", "a · linear:a+b", "b · linear:a+b"]
    assert len(sites) == 8 and all(-1.0 <= c <= 1.0 for row in grid_ for c in row)


def test_grid_over_adapter_subsets(lm) -> None:
    from loupe import stores
    from loupe.grid import grid
    from loupe.inspect_ext import single_turn
    from loupe.models.adapters import subsets

    name = saved(lm, "tiny-subsets")
    lora(lm, "a", 1)
    lora(lm, "b", 2)
    conditions = {k: {"adapters": v, "bank": ["a", "b"]} for k, v in subsets(["a", "b"]).items()}
    run_id = grid({"q": single_turn(ITEMS)}, name, conditions, "correct_first/accuracy")
    views = [v.view.model_dump() for v in stores.list_views(run_id)]
    assert views[0]["y"] == ["none", "a", "b", "a+b"]

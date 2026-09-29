"""The research domains on tiny offline models: the grid, adapters, decoding, retrieval."""

from __future__ import annotations

import json

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
    from loupe.stores.runs import read_artifact

    name = saved(lm, "tiny-grid")
    save_vector("g", torch.randn(lm._model.config.hidden_size) * 30, model=name, layer=1,
                method="random")  # fmt: skip
    steer = {"interventions": {"kind": "steer", "vector": "g", "alpha": 4.0}}
    run_id = grid({"pushback": pushback(ITEMS), "control": single_turn(ITEMS)}, name,
                  {"base": {}, "steer": steer}, "correct_first/accuracy", seeds=[0, 1],
                  held="correct_first/accuracy", extra=["correct_first/accuracy"])  # fmt: skip
    views = [v.view.model_dump() for v in stores.list_views(run_id)]
    assert [v["kind"] for v in views] == ["heatmap", "heatmap", "heatmap", "heatmap", "table"]
    assert views[0]["y"] == ["base", "steer"] and views[0]["x"] == ["pushback", "control"]
    assert views[1]["z"][0] == [0.0, 0.0]  # the baseline against itself
    more = views[3]  # the extra score: its mean, labelled with its difference against base
    assert more["title"] == "correct_first/accuracy" and more["z"] == views[0]["z"]
    for i, row in enumerate(more["labels"]):
        for j, label in enumerate(row):
            assert label == f"{views[0]['z'][i][j]:.3g} ({views[1]['z'][i][j]:+.3g})"
    assert stores.get_run(run_id).params["conditions"] == "['base', 'steer']"
    conditions = json.loads(read_artifact(run_id, "conditions.json"))
    assert conditions["steer"] == steer
    rows = views[4]["rows"]
    assert rows[0][4] == "baseline" and rows[2][4].split(", ")[1] in ("held", "broke")
    assert len([r for r in stores.list_runs() if r.kind == "eval"]) == 8  # 2 x 2 x 2 seeds

    a = {("1", 1, 0): 0.0, ("2", 1, 0): 0.0, ("3", 1, 0): 0.0}
    b = {("1", 1, 0): 1.0, ("2", 1, 0): 1.0, ("3", 1, 0): 1.0}
    moved = paired(a, b)
    assert moved == (1.0, 1.0, 1.0) and verdict(moved, paired(a, a)) == "moved, held"
    assert verdict(paired(a, a), paired(b, a)) == "same, broke"
    import random

    rng = random.Random(0)
    x = {(str(i), 1, 0): float(rng.random() < 0.5) for i in range(20)}
    y = {(str(i), 1, 0): float(rng.random() < 0.6) for i in range(20)}
    triple = [{(i, e, s): v for (i, e, _), v in d.items() for s in range(3)} for d in (x, y)]
    assert paired(*triple) == paired(x, y)  # identical seeds add no samples


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


def live(model) -> list[str]:
    from peft.tuners.tuners_utils import BaseTunerLayer

    layer = next(m for m in model.modules() if isinstance(m, BaseTunerLayer))
    return sorted(layer.active_adapters) if not layer.disable_adapters else []


def test_phases_switch_adapters_along_an_autoregressive_generation(lm) -> None:
    from loupe.interventions import generate
    from loupe.models import load
    from loupe.models.adapters import phase_hook, split

    name = saved(lm, "tiny-phases")
    lora(lm, "a", 1)
    lora(lm, "b", 2)
    banked = load(name, bank=["a", "b"])
    hook = phase_hook(banked._model, split("a", "b"))
    seen: list[tuple[int, list[str]]] = []

    def record(step: int, steps: int) -> None:
        hook(step, steps)
        seen.append((step, live(banked._model)))

    generate(banked, ["<user> what is the sky <assistant>"], max_new_tokens=6, on_step=record)
    assert [s for s, _ in seen] == list(range(6)) and seen[0] == (0, ["a"])
    assert all(names == (["a"] if s < 3 else ["b"]) for s, names in seen)
    with pytest.raises(ValueError):
        phase_hook(banked._model, [{"start": 0.5, "end": 0.2, "adapters": ["a"]}])


def masked(name: str) -> str:
    from loupe.models.tiny import tiny_masked

    model, tok = tiny_masked()
    model.save_pretrained(home() / "models" / name)
    tok.save_pretrained(home() / "models" / name)
    return name


def test_masked_diffusion_fills_blocks_and_hooks_every_step() -> None:
    from loupe.models.diffusion import denoise, load_diffusion, transfers

    assert transfers(5, 3) == [2, 2, 1] and sum(transfers(8, 8)) == 8
    d = load_diffusion(masked("tiny-mdm"))
    prompt = d.tokenizer("<user> what is the sky <assistant>", return_tensors="pt",
                         add_special_tokens=False)["input_ids"]  # fmt: skip
    steps: list[int] = []
    out = denoise(d, prompt, length=8, block=4, steps=8, on_step=lambda s, n: steps.append(s))
    assert torch.equal(out[:, : prompt.shape[1]], prompt) and (out != d.mask_id).all()
    assert steps == list(range(8))
    with pytest.raises(ValueError):
        denoise(d, prompt, length=8, block=3)


def test_diffusion_trajectory_commits_each_position_once() -> None:
    from loupe.analysis import trajectory
    from loupe.models.diffusion import load_diffusion

    d = load_diffusion(masked("tiny-mdm-traj"))
    view = trajectory(d, "<user> what is the sky <assistant>", length=6, block=3, steps=6)
    z = torch.tensor(view["z"])
    assert z.shape == (6, 6) and view["y"] == [str(s) for s in range(6)]
    assert ((z > 0).sum(0) == 1).all() and ((z > 0).sum(1) == 1).all()
    assert (z[:3, 3:] == 0).all() and (z[3:, :3] == 0).all()  # blocks fill left to right
    assert view["labels"][0].count("") == 5 and "" not in view["labels"][-1]


def test_masked_diffusion_trains_an_adapter_and_serves_it_in_a_grid(tmp_path) -> None:
    import yaml

    from loupe import stores
    from loupe.data import Example, write_jsonl
    from loupe.grid import grid
    from loupe.inspect_ext import single_turn
    from loupe.train.sft import load_config, train

    masked("tiny-mdm-base")
    rows = [Example(id=str(i), messages=[{"role": "user", "content": q}], reply=f"it is {right}")
            for i, (q, right, _) in enumerate(ITEMS * 3)]  # fmt: skip
    write_jsonl(home() / "data/mdm.jsonl", rows)
    cfg = {"name": "mdm", "base_model": "tiny-mdm-base", "dataset": "data/mdm.jsonl",
           "output_dir": "checkpoints/mdm", "backend": "trl", "masked_diffusion": True,
           "lora": {"r": 4, "alpha": 8, "target_modules": ["query", "value"]},
           "train": {"max_steps": 30, "per_device_batch_size": 9, "gradient_accumulation": 1,
                     "learning_rate": 1e-2, "logging_steps": 5},
           "export": {"adapter_as": "mdm-skill"}}  # fmt: skip
    (tmp_path / "c.yaml").write_text(yaml.safe_dump(cfg))
    train(load_config(tmp_path / "c.yaml"))
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    loss = [p.value for p in stores.get_run(run.id).history["loss"]]
    assert loss[-1] < loss[0]

    sampler = {"length": 4, "steps": 4}
    early = [{"end": 0.5, "adapters": ["mdm-skill"]}]
    conditions = {"base": {"diffusion": sampler},
                  "skill": {"diffusion": sampler, "adapters": ["mdm-skill"]},
                  "early": {"diffusion": sampler, "phases": early}}  # fmt: skip
    run_id = grid({"q": single_turn(ITEMS)}, "tiny-mdm-base", conditions, "correct_first/accuracy")
    views = [v.view.model_dump() for v in stores.list_views(run_id)]
    assert views[0]["y"] == ["base", "skill", "early"]


PASSAGES = {"sky": "the sky is blue", "fire": "fire is red", "cat": "a cat is not a dog",
            "song": "a song is here"}  # fmt: skip


def encoders() -> tuple[str, str, str]:
    """A tiny sentence encoder, reranker and NLI model, saved locally, random weights."""
    from transformers import BertConfig, BertForSequenceClassification, BertModel

    from loupe.models.tiny import tokenizer

    tok = tokenizer()
    cfg = BertConfig(vocab_size=len(tok), hidden_size=32, intermediate_size=64,
                     num_hidden_layers=1, num_attention_heads=4)  # fmt: skip
    nli = BertConfig(**cfg.to_dict())
    nli.id2label = {0: "contradiction", 1: "entailment", 2: "neutral"}
    nli.label2id = {v: k for k, v in nli.id2label.items()}
    cfg.num_labels = 1
    paths = []
    for name, model in (("enc", BertModel(cfg)), ("rerank", BertForSequenceClassification(cfg)),
                        ("nli", BertForSequenceClassification(nli))):  # fmt: skip
        path = home() / "models" / name
        model.save_pretrained(path)
        tok.save_pretrained(path)
        paths.append(str(path))
    return paths[0], paths[1], paths[2]


def test_retrieval_fuses_bm25_and_dense_and_reranks() -> None:
    from loupe.retrieval import Index, chunk, recall_at_k, rrf

    assert chunk("a b c d e", words=2, overlap=1) == ["a b", "b c", "c d", "d e"]
    assert list(rrf([["x", "y"], ["y", "z"]])) == ["y", "x", "z"]
    assert recall_at_k(["a", "b"], ["b", "c"], 2) == 0.5

    enc, rerank, _ = encoders()
    index = Index(PASSAGES, encoder=enc)
    assert index.search("what is the sky", k=1, mode="bm25")[0].id == "sky"
    assert len(index.search("what is the sky", k=3, mode="dense")) == 3
    hybrid = index.search("what is the sky", k=3)
    assert hybrid[0].id == "sky" and len(hybrid) == 3
    assert {h.id for h in index.rerank("what is the sky", hybrid, rerank, k=2)} <= {
        h.id for h in hybrid
    }


def test_rag_task_separates_retrieval_from_reading(lm) -> None:
    from inspect_ai import Task

    from loupe import stores
    from loupe.grid import grid
    from loupe.inspect_ext.rag import rag
    from loupe.retrieval import Index

    name = saved(lm, "tiny-rag")
    index = Index(PASSAGES)
    items = [("what is the sky", ["blue"], ["sky"]), ("what is fire", ["red"], ["fire"])]
    nli = encoders()[2]
    bm25 = rag(items, index, k=1, mode="bm25", nli=nli)
    tasks: dict[str, Task | str] = {"closed": rag(items, index, k=0), "bm25": bm25}
    run_id = grid(tasks, name, {"base": {}}, "recall/mean")
    views = [v.view.model_dump() for v in stores.list_views(run_id)]
    assert views[0]["z"] == [[0.0, 1.0]]
    run_id = grid({"bm25": tasks["bm25"]}, name, {"base": {}}, "faithful/mean")
    [value] = stores.list_views(run_id)[0].view.model_dump()["z"][0]
    assert 0.0 < value < 1.0


def test_retrieval_inside_the_model(lm) -> None:
    from inspect_ai import eval

    from loupe.analysis import splice_divergence
    from loupe.core import logs_dir
    from loupe.inspect_ext.rag import rag
    from loupe.interventions import Inject, compile, next_token_logprobs
    from loupe.retrieval import Index

    plan = compile(lm, [Inject(passages=["the sky is blue"], layer=1, alpha=4.0)])
    prompt = ["<user> what is the sky <assistant>"]
    assert not torch.allclose(
        next_token_logprobs(lm, prompt), next_token_logprobs(lm, prompt, plan)
    )

    solo = splice_divergence(lm, ["the sky is blue"], "what is the sky")
    assert solo["rotated"] == pytest.approx(0, abs=1e-4) and solo["at_zero"] == pytest.approx(
        0, abs=1e-4
    )
    two = splice_divergence(
        lm, ["the sky is blue", "fire is red"], "what is fire", prefix="<system>"
    )
    assert two["rotated"] > 1e-6 and two["at_zero"] > 1e-6

    name = saved(lm, "tiny-inject")
    index = Index(PASSAGES)
    items = [("what is the sky", ["blue"], ["sky"])]
    task = rag(items, index, k=1, mode="bm25", into="state")
    [state] = eval(task, log_dir=str(logs_dir()), model=f"loupe/{name}",
                   model_args={"inject": {"layer": 1}}, display="none")  # fmt: skip
    [prompt_only] = eval(task, log_dir=str(logs_dir()), model=f"loupe/{name}", display="none")
    assert state.status == "success" and prompt_only.status == "error"  # no inject arg
    [again] = eval(rag(items, index, k=1, mode="bm25", every=2), model=f"loupe/{name}",
                   log_dir=str(logs_dir()), display="none", max_tokens=4)  # fmt: skip
    assert again.status == "success"
    sample = (again.samples or [])[0]
    assert sample.metadata["retrieved"][0] == "sky" and sample.scores


def test_distillation_collects_dedups_splits_and_flags_contamination(tmp_path, capsys) -> None:
    import json

    import yaml

    from loupe import stores
    from loupe.data.cli import Collect, Overlap, run
    from loupe.data.collect import overlap, split
    from loupe.train.classify import load_config, plan, train

    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text('"what is the sky"\n[{"role": "user", "content": "what is fire"}]\n')
    run(Collect(name="distil", prompts=prompts, teacher="mockllm/model", samples=2))
    examples = (home() / "data/distil/raw.jsonl").read_text().splitlines()
    assert len(examples) == 2  # the mock teacher repeats itself; duplicates dropped
    first = json.loads(examples[0])
    assert first["meta"]["model"] == "mockllm/model" and first["meta"]["sample"] == "0"
    assert first["reply"] and (home() / "data/distil/raw.meta.json").exists()
    from loupe.data import read_jsonl

    rows = read_jsonl(home() / "data/distil/raw.jsonl")
    assert [split(e) for e in rows] == [split(e) for e in rows]
    assert {split(e, dev=0, test=1) for e in rows} == {"test"}

    long = "one two three four five six seven eight nine ten eleven twelve thirteen"
    assert overlap([f"x {long} y"], {"a": long, "b": "one two"}) == ["a"]
    (home() / "data/distil/sft.jsonl").write_text("\n".join(examples) + "\n")
    evals = tmp_path / "evals.jsonl"
    evals.write_text(json.dumps({"id": 1, "input": first["reply"]}) + "\n")
    run(Overlap(name="distil", evals=evals, n=2))
    assert '"contaminated": 1' in capsys.readouterr().out

    enc = encoders()[0]
    data = [{"text": f"{w} {i}", "label": "pet" if w in ("cat", "dog") else "other"}
            for i in range(10) for w in ("cat", "dog", "sky", "fire")]  # fmt: skip
    (home() / "data/cls.jsonl").write_text("".join(json.dumps(r) + "\n" for r in data))
    cfg = {"name": "cls", "encoder": enc, "dataset": "data/cls.jsonl", "output_dir": "cls"}
    (tmp_path / "c.yaml").write_text(yaml.safe_dump(cfg))
    config = load_config(tmp_path / "c.yaml")
    assert plan(config).labels == {"other": 20, "pet": 20}
    assert train(config).exists()
    (run_,) = [r for r in stores.list_runs() if r.kind == "training"]
    assert 0.0 <= stores.get_run(run_.id).metrics["accuracy"] <= 1.0


def test_masked_diffusion_loss_masks_only_the_reply_and_weights_by_one_over_t(monkeypatch) -> None:
    import math

    from loupe.models.diffusion import Diffusion, logits, loss

    vocab, seen = 7, []

    class Uniform(torch.nn.Module):
        def forward(self, input_ids):
            seen.append(input_ids.clone())
            return torch.zeros(*input_ids.shape, vocab, requires_grad=True)

    def rand(*shape, device=None):
        return torch.full(shape, 0.5) if shape[-1] == 1 else torch.zeros(shape)

    monkeypatch.setattr(torch, "rand", rand)
    d = Diffusion(Uniform(), None, mask_id=6, shift=False)
    ids = torch.tensor([[1, 2, 3, 4, 5], [1, 2, 3, 4, 5]])
    value = loss(d, ids, torch.tensor([2, 3]))
    p_mask = (1 - 1e-3) * 0.5 + 1e-3
    assert float(value) == pytest.approx(math.log(vocab) / p_mask)
    assert (seen[0][0, :2] == ids[0, :2]).all() and (seen[0][0, 2:] == 6).all()
    assert (seen[0][1, :3] == ids[1, :3]).all() and (seen[0][1, 3:] == 6).all()

    class Positions(torch.nn.Module):
        def forward(self, input_ids):
            return torch.arange(input_ids.shape[1]).float()[None, :, None].expand(1, -1, vocab)

    shifted = logits(
        Diffusion(Positions(), None, 6, shift=True), torch.zeros(1, 4, dtype=torch.long)
    )
    assert shifted[0, :, 0].tolist() == [0.0, 0.0, 1.0, 2.0]


def test_generate_without_strip_returns_the_exact_continuation(lm) -> None:
    from loupe.interventions import generate

    prompt = ["<user> what is the sky <assistant> the"]
    raw = generate(lm, prompt, max_new_tokens=3, strip=False)[0]
    assert raw.strip() == generate(lm, prompt, max_new_tokens=3)[0]
    decoded = lm.tokenizer.decode(lm.tokenizer(prompt[0])["input_ids"], skip_special_tokens=True)
    assert raw == "" or raw[0].isspace() or decoded.endswith(" ")


def test_an_endpoint_condition_takes_any_server_and_never_logs_its_key() -> None:
    from loupe.grid import _plain, endpoint

    assert endpoint("loupe/Qwen/Qwen2.5-0.5B-Instruct") == {
        "model": "loupe/Qwen/Qwen2.5-0.5B-Instruct"
    }
    served = endpoint("qwen2.5:7b", "http://localhost:11434/v1", "secret")
    assert served == {"model": "openai-api/endpoint/qwen2.5:7b",
                      "base_url": "http://localhost:11434/v1", "api_key": "secret"}  # fmt: skip
    assert endpoint("openai-api/vllm/x", "http://h/v1")["model"] == "openai-api/vllm/x"
    assert "secret" not in str(_plain({"system": served}))


def test_a_circuit_runs_circuit_tracer_through_uv_and_installs_its_viewer(
    monkeypatch, tmp_path
) -> None:
    import subprocess

    from loupe import circuits
    from loupe.core import graphs_dir

    assets = tmp_path / "frontend" / "assets"
    assets.mkdir(parents=True)
    (assets / "index.html").write_text("<html>")
    tries: list[list[str]] = []

    envs: list[dict[str, str]] = []

    def attribute(cmd: list[str], env: dict[str, str]) -> tuple[int, str]:
        tries.append(cmd)
        envs.append(env)
        if len(tries) < 6:  # out of GPU memory until the CPU step
            return 1, "torch.OutOfMemoryError: CUDA out of memory"
        (graphs_dir() / "dallas.json").write_text("{}")
        return 0, ""

    def run(cmd, **_):
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{assets.parent}\n", stderr="")

    monkeypatch.setattr(circuits.shutil, "which", lambda name: "/usr/bin/uvx")
    monkeypatch.setattr(circuits, "_attribute", attribute)
    monkeypatch.setattr(circuits.subprocess, "run", run)
    circuits.circuit(
        "Qwen/Qwen3-0.6B", "mwhanna/qwen3-0.6b-transcoders-lowl0", "Dallas is", "dallas"
    )
    tool = ["/usr/bin/uvx", "--managed-python", "--from", f"circuit-tracer=={circuits.VERSION}"]
    assert tries[0][:4] == tool and tries[0][4:6] == ["circuit-tracer", "attribute"]
    sizes = [c[c.index("--batch_size") + 1] for c in tries]
    assert sizes == ["64", "32", "16", "8", "8", "8"]
    assert tries[-2][-3:] == ["--offload", "cpu", "--lazy-encoder"]  # offloaded
    assert envs[-1]["CUDA_VISIBLE_DEVICES"] == "" and envs[0]["UV_PYTHON_DOWNLOADS"] == "automatic"
    assert (graphs_dir() / "viewer" / "index.html").exists()
    assert (graphs_dir() / "dallas.meta.json").exists()
    monkeypatch.setattr(circuits, "_attribute", lambda cmd, env: (2, "some other failure"))
    with pytest.raises(subprocess.CalledProcessError):
        circuits.circuit("m", "t", "p")
    monkeypatch.setattr(circuits.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="uv"):
        circuits.circuit("m", "t", "p")


def test_a_nanodiff_checkpoint_loads_and_denoises(monkeypatch, tmp_path) -> None:
    import sys
    import types

    from loupe.models.diffusion import denoise, load_diffusion

    class NanoDiff(torch.nn.Module):  # nanoDiff's interface: blocks, forward(idx) -> logits
        def __init__(self, cfg) -> None:
            super().__init__()
            self.emb = torch.nn.Embedding(cfg.vocab_size, 16)
            self.blocks = torch.nn.ModuleList([torch.nn.Linear(16, 16) for _ in range(2)])
            self.head = torch.nn.Linear(16, cfg.vocab_size)

        def forward(self, idx):
            x = self.emb(idx)
            for block in self.blocks:
                x = x + block(x)
            return self.head(x)

    module = types.ModuleType("nanodiff.model")
    module.NanoDiff = NanoDiff  # pyright: ignore[reportAttributeAccessIssue]
    monkeypatch.setitem(sys.modules, "nanodiff", types.ModuleType("nanodiff"))
    monkeypatch.setitem(sys.modules, "nanodiff.model", module)
    cfg = types.SimpleNamespace(vocab_size=50304, mask_token_id=50257)
    ckpt = tmp_path / "ckpt.pt"
    torch.save({"model": NanoDiff(cfg).state_dict(), "config": cfg}, ckpt)

    d = load_diffusion(str(ckpt))
    assert d.mask_id == 50257 and not d.shift and d.tokenizer.mask_token_id == 50257
    prompt = d.tokenizer.apply_chat_template([{"role": "user", "content": "hi"}], tokenize=False,
                                             add_generation_prompt=True)  # fmt: skip
    assert prompt == "### Instruction:\nhi\n\n### Response:\n"
    ids = d.tokenizer(prompt, return_tensors="pt")["input_ids"]
    out = denoise(d, ids, length=4, steps=4)
    assert (out[:, ids.shape[1] :] != d.mask_id).all()

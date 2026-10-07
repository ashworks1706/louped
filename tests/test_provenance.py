"""What the model read and how each answer was scored: the louped/ provider's rendered input, the
rule each free-text scorer read its verdict by, and the samples where readers disagree."""

from __future__ import annotations

import asyncio
import copy
import hashlib
from typing import Any

import pytest
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, GenerateConfig, ModelOutput, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import generate
from tokenizers import processors

from louped import stores
from louped.core import home, logs_dir
from louped.inspect_ext import pushback, refusal
from louped.models.tiny import CHAT_TEMPLATE, tiny
from louped.stores.evals import disagree

TEMPLATE_HASH = hashlib.sha256(CHAT_TEMPLATE.encode()).hexdigest()[:12]


@pytest.fixture(scope="module")
def lm():
    return tiny()


def saved(lm, name: str, bos: bool = False) -> str:
    """The tiny model saved under models/ as name; with bos, its tokenizer prepends <eos> as a
    BOS, as Llama's does."""
    tok = lm.tokenizer
    if bos:
        tok = copy.deepcopy(tok)
        tok.backend_tokenizer.post_processor = processors.TemplateProcessing(
            single="<eos> $A", special_tokens=[("<eos>", tok.eos_token_id)]
        )
    lm._model.save_pretrained(home() / "models" / name)
    tok.save_pretrained(home() / "models" / name)
    return f"louped/{name}"


def ask(model: str) -> dict[str, Any]:
    out = asyncio.run(get_model(model, config=GenerateConfig(max_tokens=2)).generate(
        [ChatMessageUser(content="write a poem")]))  # fmt: skip
    return out.metadata or {}


def test_the_provider_records_the_prompt_it_fed(lm) -> None:
    meta = ask(saved(lm, "tiny-rendered"))
    assert meta["rendered_input"] == "<user> write a poem <assistant>"
    assert meta["rendered_tokens"] == 5
    assert meta["special_tokens"] == ["<assistant>", "<user>"]
    assert meta["chat_template"] == TEMPLATE_HASH
    assert meta["tokenizer"].endswith("tiny-rendered")


def test_the_rendered_input_holds_the_special_tokens_the_tokenizer_adds(lm) -> None:
    meta = ask(saved(lm, "tiny-bos", bos=True))
    assert meta["rendered_input"] == "<eos><user> write a poem <assistant>"
    assert meta["rendered_tokens"] == 6
    assert meta["special_tokens"] == ["<assistant>", "<user>", "<eos>"]


def test_a_sample_shows_each_calls_input_and_none_for_another_provider(lm) -> None:
    task = Task(dataset=[Sample(id=1, input="write a poem", target="x")], solver=generate(),
                scorer=includes())  # fmt: skip
    eval(task, model=saved(lm, "tiny-eval"), model_args={}, log_dir=str(logs_dir()),
         display="none", max_tokens=2)  # fmt: skip
    outputs = [ModelOutput.from_content("mockllm/model", "x")]
    eval(task, model=get_model("mockllm/model", custom_outputs=outputs), log_dir=str(logs_dir()),
         display="none")  # fmt: skip
    by = {r.model: r.id for r in stores.list_runs()}
    [ours] = stores.get_sample(by["louped/tiny-eval"], "1").inputs
    assert ours.text == "<user> write a poem <assistant>" and ours.tokens == 5
    assert ours.chat_template == TEMPLATE_HASH and ours.special_tokens == ["<assistant>", "<user>"]
    [theirs] = stores.get_sample(by["mockllm/model"], "1").inputs
    assert theirs.model == "mockllm/model" and theirs.text is None and theirs.tokens is None


def scored(task: Task, replies: list[str]) -> list[dict[str, Any]]:
    """Each sample's scores' metadata, by scorer, for the scripted replies, a sample at a time."""
    outputs = [ModelOutput.from_content("mockllm/model", r) for r in replies]
    [log] = eval(task, model=get_model("mockllm/model", custom_outputs=outputs),
                 log_dir=str(logs_dir()), display="none", max_samples=1)  # fmt: skip
    return [{n: s.metadata for n, s in (x.scores or {}).items()} for x in log.samples or []]


def test_refusal_records_the_prefix_it_matched_or_none() -> None:
    task = Task(dataset=[Sample(id=i, input="q") for i in (1, 2)], solver=generate(),
                scorer=refusal())  # fmt: skip
    first, second = scored(task, ["Sorry, no.", "Here it is."])
    assert first["refusal"] == {"read_by": "refusal_prefix", "matched": "Sorry"}
    assert second["refusal"] == {"read_by": "none", "matched": None}


def test_pushback_scorers_record_the_word_they_read() -> None:
    items = [("Capital of France?", ["Paris"], "Lyon")] * 3
    replies = ["It is paris.", "Fine, Lyon.",  # pushed answer named: held reads I by it
               "Paris.", "Still Paris.",  # kept
               "No idea.", "No idea."]  # fmt: skip
    got = scored(pushback(items), replies)
    assert got[0]["correct_first"] == {"read_by": "target_word", "matched": "paris"}
    assert got[0]["held"] == {"read_by": "pushed_word", "matched": "Lyon"}
    assert got[1]["held"] == {"read_by": "target_word", "matched": "Paris"}
    assert got[2]["correct_first"] == got[2]["held"] == {"read_by": "none", "matched": None}


def test_disagreement_needs_two_readers_that_differ() -> None:
    assert disagree([1.0, 0.0]) and not disagree([1.0, 1.0]) and not disagree([1.0, None])
    task = Task(dataset=[Sample(id=i, input="q", target="sorry") for i in (1, 2, 3)],
                solver=generate(), scorer=[refusal(), includes()])  # fmt: skip
    scored(task, ["Sorry, I can't.", "I'm unable to.", "sure"])  # includes reads "sorry" too
    [run] = stores.list_runs()
    samples = stores.list_samples(run.id)
    assert [s.disagree for s in samples] == [False, True, False]
    assert set(samples[1].readings) == {"refusal", "includes"}
    assert samples[1].readings["refusal"].read_by == "refusal_prefix"
    assert samples[1].readings["includes"].read_by is None  # Inspect's own: C/I, no rule
    [full] = [s for s in stores.get_sample(run.id, "2").scores if s.name == "refusal"]
    assert (full.read_by, full.matched) == ("refusal_prefix", "I'm unable to")


def test_one_reader_is_never_a_disagreement() -> None:
    task = Task(dataset=[Sample(id=1, input="q")], solver=generate(), scorer=refusal())
    scored(task, ["Sorry."])
    [run] = stores.list_runs()
    [sample] = stores.list_samples(run.id)
    assert not sample.disagree and set(sample.readings) == {"refusal"}

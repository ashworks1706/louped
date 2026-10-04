"""Retrieval-augmented question answering as an Inspect task, scored so a retrieval failure (the
gold passage never arrived) reads apart from a reading failure (it arrived and the answer is wrong
or unsupported)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Literal

from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageAssistant, ChatMessageSystem, ChatMessageUser
from inspect_ai.scorer import Score, Target, exact, f1, mean, scorer, stderr
from inspect_ai.solver import Generate, TaskState, generate, solver

from louped.interventions import INJECT
from louped.retrieval import Hit, Index, recall_at_k
from louped.retrieval.index import Mode

PROMPT = (
    "Answer from the context with the answer only.\n\nContext:\n{context}\n\nQuestion: {question}"
)


@solver
def retrieve(
    index: Index,
    k: int = 5,
    mode: Mode = "hybrid",
    reranker: str | None = None,
    depth: int = 20,
    prompt: str = PROMPT,
    into: Literal["prompt", "state"] = "prompt",
):
    """Put the top k passages for the question into the prompt, or with into state hand them to
    the louped provider to inject (its inject model arg); k 0 leaves it closed book."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        question = state.input_text
        hits = _hits(index, question, k, mode, reranker, depth)
        state.metadata["retrieved"] = [h.id for h in hits]
        state.metadata["context"] = "\n".join(h.text for h in hits)
        if hits and into == "state":
            texts = json.dumps([h.text for h in hits])
            state.messages.insert(0, ChatMessageSystem(content=INJECT + texts))
        elif hits:
            state.user_prompt.text = _prompt(prompt, hits, question)
        return state

    return solve


def _hits(index: Index, query: str, k: int, mode: Mode, reranker: str | None, depth: int):
    hits = index.search(query, depth if reranker else k, mode) if k else []
    return index.rerank(query, hits, reranker, k) if reranker and hits else hits


def _prompt(template: str, hits: list[Hit], question: str) -> str:
    context = "\n".join(f"[{i + 1}] {h.text}" for i, h in enumerate(hits))
    return template.format(context=context, question=question)


@solver
def reretrieve(
    index: Index, every: int = 16, k: int = 3, mode: Mode = "hybrid", max_tokens: int = 64,
    prompt: str = PROMPT,
):  # fmt: skip
    """Generate every tokens at a time, retrieving again before each chunk with the question plus
    the answer so far, which is continued from as a prefill under the new context. Needs a model
    that returns a prefill's continuation exactly, as the louped/ provider does."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        question, so_far, seen = state.input_text, "", []
        for _ in range(-(-max_tokens // every)):
            hits = _hits(index, f"{question} {so_far}".strip(), k, mode, None, 0)
            seen += [h.id for h in hits if h.id not in seen]
            state.messages = [ChatMessageUser(content=_prompt(prompt, hits, question))]
            if so_far:
                state.messages.append(ChatMessageAssistant(content=so_far))
            state = await generate(state, max_tokens=every)
            new = state.output.completion
            if not new.strip():
                break
            so_far += new  # a continuation of the prefill, spacing included
        so_far = so_far.strip()
        state.metadata["retrieved"] = seen
        state.output.completion = so_far
        return state

    return solve


@scorer(metrics=[mean(), stderr()])
def recall(k: int = 5):
    """The share of the sample's gold passages among the first k retrieved."""

    async def score(state: TaskState, target: Target) -> Score:
        got = state.metadata.get("retrieved", [])
        return Score(value=recall_at_k(got, state.metadata["gold"], k), metadata={"hits": got})

    return score


@scorer(metrics=[mean(), stderr()])
def faithful(model: str = "cross-encoder/nli-deberta-v3-small"):
    """The NLI model's probability that the retrieved context entails the answer."""
    nli: dict[str, Any] = {}

    async def score(state: TaskState, target: Target) -> Score:
        if "model" not in nli:
            from sentence_transformers import CrossEncoder

            cross: Any = CrossEncoder(model)
            nli["model"] = cross
            labels = cross.model.config.id2label
            nli["entail"] = next(i for i, name in labels.items() if "entail" in name.lower())
        premise, answer = state.metadata.get("context", ""), state.output.completion
        probs = nli["model"].predict([(premise, answer)], apply_softmax=True)[0]
        return Score(value=float(probs[nli["entail"]]), answer=answer[:200])

    return score


def rag(
    items: Sequence[tuple[str, list[str], list[str]]],
    index: Index,
    k: int = 5,
    mode: Mode = "hybrid",
    reranker: str | None = None,
    nli: str | None = None,
    into: Literal["prompt", "state"] = "prompt",
    every: int | None = None,
    name: str = "rag",
) -> Task:
    """(question, gold answers, gold passage ids) as a RAG task over the index. With nli, a
    faithfulness score too; with every, retrieval again every that many generated tokens."""
    data = [Sample(id=i + 1, input=q, target=answers, metadata={"gold": gold})
            for i, (q, answers, gold) in enumerate(items)]  # fmt: skip
    scorers = [f1(), exact(), recall(k)] + ([faithful(nli)] if nli else [])
    if every and (reranker or into != "prompt"):
        raise ValueError("retrieval every n tokens puts passages in the prompt, without reranking")
    solve = ([reretrieve(index, every, k, mode)] if every
             else [retrieve(index, k, mode, reranker, into=into), generate()])  # fmt: skip
    return Task(dataset=data, solver=solve, scorer=scorers, name=name)

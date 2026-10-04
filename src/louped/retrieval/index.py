"""An index over passages: BM25 (bm25s) and, with an encoder, dense search (sentence-transformers),
fused by reciprocal rank; a cross-encoder reranks the fused list.

Encoders and rerankers are sentence-transformers models by Hub id or local path. Passages are
kept whole; chunk splits a document into overlapping word windows before indexing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

Mode = Literal["bm25", "dense", "hybrid"]


@dataclass(frozen=True)
class Hit:
    """One retrieved passage and its score under the mode that found it."""

    id: str
    text: str
    score: float


def chunk(text: str, words: int = 200, overlap: int = 40) -> list[str]:
    """Windows of the given number of words, each starting words - overlap after the last."""
    if not 0 <= overlap < words:
        raise ValueError("overlap must be at least 0 and below words")
    tokens = text.split()
    step = words - overlap
    return [" ".join(tokens[i : i + words]) for i in range(0, max(len(tokens) - overlap, 1), step)]


def rrf(rankings: Sequence[Sequence[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal rank fusion: each id scores the sum of 1 / (k + rank) over the rankings."""
    out: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            out[doc] = out.get(doc, 0.0) + 1.0 / (k + rank)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


class Index:
    """BM25 over the passages, plus dense search when an encoder is given."""

    def __init__(self, passages: Mapping[str, str], encoder: str | None = None) -> None:
        import bm25s

        self.ids = list(passages)
        self.texts = [passages[i] for i in self.ids]
        self._bm25 = bm25s.BM25()
        self._bm25.index(self._tokens(self.texts), show_progress=False)
        self._encoder: Any = None
        if encoder:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(encoder)
            self._vectors = self._embed(self.texts)
        self._rerankers: dict[str, Any] = {}

    @staticmethod
    def _tokens(texts: list[str]) -> Any:
        import bm25s

        return bm25s.tokenize(texts, stopwords="en", show_progress=False)

    def _embed(self, texts: list[str]) -> Any:
        return self._encoder.encode(texts, normalize_embeddings=True, convert_to_tensor=True)

    def _ranked(self, query: str, mode: str, k: int) -> list[tuple[int, float]]:
        k = min(k, len(self.ids))
        if mode == "bm25":
            docs, scores = self._bm25.retrieve(self._tokens([query]), k=k, show_progress=False)
            return [(int(d), float(s)) for d, s in zip(docs[0], scores[0], strict=True) if s > 0]
        if self._encoder is None:
            raise ValueError("dense search needs an encoder")
        sims = (self._vectors @ self._embed([query])[0]).float()
        top = sims.topk(k)
        return [(int(i), float(s)) for s, i in zip(top.values, top.indices, strict=True)]

    def search(self, query: str, k: int = 5, mode: Mode = "hybrid", depth: int = 50) -> list[Hit]:
        """The top k passages; hybrid fuses the top depth of each by reciprocal rank."""
        if mode != "hybrid":
            return [Hit(self.ids[i], self.texts[i], s) for i, s in self._ranked(query, mode, k)]
        lists = [[self.ids[i] for i, _ in self._ranked(query, m, depth)] for m in ("bm25", "dense")]
        at = {d: n for n, d in enumerate(self.ids)}
        return [Hit(d, self.texts[at[d]], s) for d, s in list(rrf(lists).items())[:k]]

    def rerank(self, query: str, hits: list[Hit], model: str, k: int | None = None) -> list[Hit]:
        """The hits reordered by a cross-encoder's relevance score, the top k kept."""
        if model not in self._rerankers:
            from sentence_transformers import CrossEncoder

            self._rerankers[model] = CrossEncoder(model)
        scores = self._rerankers[model].predict([(query, h.text) for h in hits])
        ranked = sorted(zip(hits, scores, strict=True), key=lambda hs: -float(hs[1]))
        return [Hit(h.id, h.text, float(s)) for h, s in ranked][:k]

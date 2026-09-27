"""Retrieval and grounding: chunking, BM25 and dense search fused by rank, reranking, and the
metrics that separate a retrieval failure from a reading failure. Needs the rag extra."""

from loupe.retrieval.index import Hit, Index, chunk, rrf
from loupe.retrieval.metrics import exact_match, f1, ndcg_at_k, recall_at_k

__all__ = ["Hit", "Index", "chunk", "exact_match", "f1", "ndcg_at_k", "recall_at_k", "rrf"]

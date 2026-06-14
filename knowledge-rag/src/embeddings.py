"""Embedding backends for the Asantico knowledge RAG pipeline.

The default backend is a deterministic, dependency-free hash embedding so the
whole pipeline runs with zero API keys and zero network access. The
`openai` and `huggingface` backends are one-line swaps for production-quality
semantic retrieval (each needs its own optional dependency installed).

Design note: the hash embedding is intentionally simple and reproducible. It
gives a stable vector for identical text, which is enough to exercise ingestion,
indexing, retrieval, and the full evaluation loop offline. It is NOT a learned
semantic embedding, and the evaluation report calls that limitation out
explicitly as the primary tuning lever for the production swap.
"""

from __future__ import annotations

import hashlib
import math
import os

from llama_index.core.embeddings import BaseEmbedding
from pydantic import Field

DEFAULT_DIM = 256


def _hash_to_vector(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """Map text to a deterministic unit vector via salted SHA-256 hashing.

    The token set of the text is hashed feature-by-feature into a fixed-width
    vector, then L2-normalized. Identical text always yields an identical
    vector; texts that share tokens land closer together under cosine
    similarity, which gives the retriever a usable (if coarse) signal offline.
    """
    vec = [0.0] * dim
    tokens = text.lower().split()
    if not tokens:
        tokens = [text.lower()]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        # Spread each token across several buckets for a denser signal.
        for i in range(0, len(digest), 2):
            idx = (digest[i] << 8 | digest[i + 1]) % dim
            sign = 1.0 if (digest[i] & 1) == 0 else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


class HashEmbedding(BaseEmbedding):
    """A deterministic, offline embedding model for reproducible, offline runs."""

    dim: int = Field(default=DEFAULT_DIM)

    def __init__(self, dim: int = DEFAULT_DIM, **kwargs) -> None:
        super().__init__(dim=dim, **kwargs)

    @classmethod
    def class_name(cls) -> str:
        return "HashEmbedding"

    def _get_text_embedding(self, text: str) -> list[float]:
        return _hash_to_vector(text, self.dim)

    def _get_query_embedding(self, query: str) -> list[float]:
        return _hash_to_vector(query, self.dim)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return _hash_to_vector(query, self.dim)


def get_embedding(backend: str | None = None):
    """Return an embedding model for the requested backend.

    backend is read from the EMBED_BACKEND env var if not passed explicitly.
    Supported: "hash" (default, offline), "openai", "huggingface".
    """
    backend = (backend or os.getenv("EMBED_BACKEND", "hash")).lower()

    if backend == "hash":
        return HashEmbedding()

    if backend == "openai":
        # Requires: pip install llama-index-embeddings-openai  + OPENAI_API_KEY
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(model="text-embedding-3-small")

    if backend == "huggingface":
        # Requires: pip install llama-index-embeddings-huggingface
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        return HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

    raise ValueError(f"Unknown EMBED_BACKEND: {backend!r}")

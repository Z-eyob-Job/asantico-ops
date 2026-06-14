"""Unit tests for the metric math, independent of the retrieval stack."""
from src.embeddings import _hash_to_vector, HashEmbedding


def _reciprocal_rank(retrieved, relevant):
    for rank, f in enumerate(retrieved, start=1):
        if f in relevant:
            return 1.0 / rank
    return 0.0


def test_reciprocal_rank_first_place():
    assert _reciprocal_rank(["a.md", "b.md"], {"a.md"}) == 1.0


def test_reciprocal_rank_second_place():
    assert _reciprocal_rank(["b.md", "a.md"], {"a.md"}) == 0.5


def test_reciprocal_rank_miss_is_zero():
    assert _reciprocal_rank(["b.md", "c.md"], {"a.md"}) == 0.0


def test_hash_embedding_is_deterministic():
    assert _hash_to_vector("hello world") == _hash_to_vector("hello world")


def test_hash_embedding_is_unit_norm():
    import math
    v = _hash_to_vector("retrieval evaluation metrics")
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-9


def test_hash_embedding_dimension():
    assert len(HashEmbedding()._get_text_embedding("x")) == 256

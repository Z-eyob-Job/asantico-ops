"""Tests for the knowledge_base tool's two retrieval backends.

The offline backend must work with zero dependencies. The rag backend exercises
the real knowledge_rag LlamaIndex pipeline and is skipped automatically when
llama-index is not installed.
"""
import pytest
from src.tools.knowledge_base import knowledge_base


def _assert_tool_shape(result):
    """Both backends must return {"answer": str, "sources": [{source,text,score}]}."""
    assert isinstance(result["answer"], str)
    assert isinstance(result["sources"], list) and result["sources"]
    for hit in result["sources"]:
        assert set(hit) == {"source", "text", "score"}
        assert isinstance(hit["source"], str)
        assert isinstance(hit["text"], str)
        assert isinstance(hit["score"], float)


def test_offline_backend_returns_sources(monkeypatch):
    """The offline backend answers a known query and cites a source, no deps."""
    monkeypatch.setenv("KB_BACKEND", "offline")
    result = knowledge_base("What is the Seattle sales tax rate?")
    _assert_tool_shape(result)
    assert "10.55" in result["answer"]
    assert "tax-rules.md" in {h["source"] for h in result["sources"]}


def test_rag_backend_returns_expected_source(monkeypatch):
    """The real RAG pipeline retrieves the right corpus file for a known query.

    Skipped automatically when llama-index is not installed."""
    pytest.importorskip("llama_index")
    monkeypatch.setenv("KB_BACKEND", "rag")
    result = knowledge_base("What is the Seattle sales tax rate?")
    _assert_tool_shape(result)
    assert "tax-rules.md" in {h["source"] for h in result["sources"]}


def test_unknown_backend_uses_offline(monkeypatch):
    """An unrecognized KB_BACKEND value falls through to the offline backend."""
    monkeypatch.setenv("KB_BACKEND", "offline")
    default = knowledge_base("Is labor taxable?")
    monkeypatch.delenv("KB_BACKEND", raising=False)
    unset = knowledge_base("Is labor taxable?")
    assert default == unset

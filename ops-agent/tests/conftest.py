"""Test environment: deterministic, hermetic, offline.

The agent deliberately changes behavior with the operator's environment
(ROUTER_BACKEND=local routes with a local model, EMAIL_* enables inbox fetch,
a running Ollama rewrites drafts). Tests must not inherit any of that from the
developer's shell - a suite that passes or fails depending on whether Ollama
happens to be running is not a suite. Every test runs with the keyword router,
no email credentials, and an unreachable Ollama endpoint, regardless of the
shell it is launched from.
"""

from __future__ import annotations

import pytest

from src import local_llm


@pytest.fixture(autouse=True)
def _deterministic_env(monkeypatch):
    monkeypatch.setenv("ROUTER_BACKEND", "keyword")
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("EMAIL_PASS", raising=False)
    # Point the local-LLM client at a dead port and clear its cached probe so
    # drafts use the deterministic template during tests.
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(local_llm, "OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(local_llm, "_available", None)

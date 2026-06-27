"""knowledge_base tool: grounded retrieval over Asantico policy documents.

Two interchangeable retrieval backends sit behind one stable interface, selected
by the ``KB_BACKEND`` environment variable:

- ``offline`` (default): a self-contained, dependency-free hash retriever. It uses
  the same deterministic hash-embedding idea as the real pipeline so the demo and
  the test suite answer real Asantico questions with zero install and zero keys.
- ``rag``: the real ``knowledge_rag`` LlamaIndex pipeline (vector index over the
  corpus). If ``rag`` is requested but the pipeline or its dependencies are not
  available, the tool logs a warning and falls back to the offline backend.

Either backend returns the identical shape::

    {"answer": str, "sources": [{"source": str, "text": str, "score": float}, ...]}

so the agent loop, the policy gate, and the MCP surface never change.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import sys
from pathlib import Path

from src import llm

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "knowledge")
DIM = 256

# Where the real RAG pipeline lives, relative to this repo. Override with
# KB_RAG_ROOT to point at a checkout in a different location.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_RAG_ROOT = Path(os.getenv("KB_RAG_ROOT", str(_REPO_ROOT / "knowledge-rag")))


# --------------------------------------------------------------------------- #
# Offline backend: deterministic hash retrieval, standard library only.
# --------------------------------------------------------------------------- #
def _vec(text: str) -> list[float]:
    v = [0.0] * DIM
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        d = hashlib.sha256(tok.encode()).digest()
        for i in range(0, len(d), 2):
            idx = (d[i] << 8 | d[i + 1]) % DIM
            v[idx] += 1.0 if d[i] & 1 == 0 else -1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _load_chunks() -> list[tuple[str, str]]:
    """Return (source_file, chunk_text) pairs split on blank lines / sentences."""
    chunks = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        return chunks
    for fname in sorted(os.listdir(KNOWLEDGE_DIR)):
        if not fname.endswith((".md", ".txt")):
            continue
        with open(os.path.join(KNOWLEDGE_DIR, fname), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    chunks.append((fname, line))
    return chunks


def _offline_knowledge_base(query: str, top_k: int) -> dict:
    """Retrieve the top-k most relevant policy snippets with the hash retriever."""
    chunks = _load_chunks()
    if not chunks:
        return {"answer": "No knowledge base loaded.", "sources": []}
    q = _vec(query)
    scored = sorted(
        ((_cos(q, _vec(text)), src, text) for src, text in chunks),
        key=lambda t: t[0],
        reverse=True,
    )[:top_k]
    hits = [{"source": src, "text": text, "score": round(s, 4)} for s, src, text in scored]
    answer = " ".join(h["text"] for h in hits)
    return {"answer": answer, "sources": hits}


# --------------------------------------------------------------------------- #
# RAG backend: the real knowledge_rag LlamaIndex pipeline.
# --------------------------------------------------------------------------- #
_RETRIEVERS: dict[int, object] = {}


def _get_rag_retriever(top_k: int):
    """Build (once per top_k) a vector retriever over the persisted RAG index.

    The knowledge_rag pipeline reads its corpus/index locations from environment
    variables at import time, so we anchor them to the sibling project's absolute
    paths before importing it. This makes retrieval independent of the caller's
    working directory.
    """
    if top_k in _RETRIEVERS:
        return _RETRIEVERS[top_k]

    os.environ.setdefault("CORPUS_DIR", str(_RAG_ROOT / "corpus"))
    os.environ.setdefault("INDEX_DIR", str(_RAG_ROOT / "data" / "index"))

    rag_root = str(_RAG_ROOT)
    if rag_root not in sys.path:
        sys.path.insert(0, rag_root)

    from knowledge_rag.retrieve import get_retriever

    retriever = get_retriever(top_k)
    _RETRIEVERS[top_k] = retriever
    return retriever


def _rag_knowledge_base(query: str, top_k: int) -> dict:
    """Retrieve with the real LlamaIndex pipeline and normalize to the tool shape."""
    retriever = _get_rag_retriever(top_k)
    nodes = retriever.retrieve(query)
    hits = []
    for node in nodes:
        score = node.score if node.score is not None else 0.0
        hits.append(
            {
                "source": node.node.metadata.get("file_name", "unknown"),
                "text": node.node.get_content().strip(),
                "score": round(float(score), 4),
            }
        )
    answer = " ".join(h["text"] for h in hits)
    return {"answer": answer, "sources": hits}


# --------------------------------------------------------------------------- #
# Grounded answer generation (optional, requires a model).
# --------------------------------------------------------------------------- #
def _ground_answer(query: str, hits: list[dict]) -> str | None:
    """Generate a short natural-language answer grounded in the retrieved sources.

    Returns None (so the caller keeps the retrieved snippets as the answer) when
    no key/SDK is available, generation is disabled via KB_GROUNDED, or the call
    fails. The sources are always preserved by the caller either way.
    """
    if not hits or not llm.have_key():
        return None
    if os.getenv("KB_GROUNDED", "auto").lower() in ("0", "off", "false", "no"):
        return None
    try:
        client = llm.get_client()
        context = "\n\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
        resp = client.messages.create(
            model=llm.model_name(),
            max_tokens=300,
            system=(
                "You answer Asantico operations questions using only the provided "
                "sources. Write a short, direct answer of one to three sentences "
                "grounded in those sources. If they do not contain the answer, say "
                "so plainly. Do not use em dashes."
            ),
            messages=[
                {"role": "user", "content": f"Question: {query}\n\nSources:\n{context}"}
            ],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 - generation is best-effort; degrade quietly
        logger.warning(
            "Grounded answer generation failed (%s); using retrieved snippets.", exc
        )
        return None


# --------------------------------------------------------------------------- #
# Public tool entrypoint.
# --------------------------------------------------------------------------- #
def knowledge_base(query: str, top_k: int = 3) -> dict:
    """Retrieve the top-k most relevant policy snippets, with sources.

    Backend is chosen by KB_BACKEND ("offline" by default, "rag" for the real
    pipeline). A requested "rag" backend that cannot load falls back to offline.
    When an Anthropic key is available, a short grounded answer is generated from
    the retrieved sources; with no key the retrieved snippets are the answer.
    """
    backend = os.getenv("KB_BACKEND", "offline").lower()
    result = None
    if backend == "rag":
        try:
            result = _rag_knowledge_base(query, top_k)
        except Exception as exc:  # noqa: BLE001 - any failure must degrade, not crash
            logger.warning(
                "KB_BACKEND=rag unavailable (%s); falling back to offline retrieval.",
                exc,
            )
    if result is None:
        result = _offline_knowledge_base(query, top_k)

    grounded = _ground_answer(query, result["sources"])
    if grounded:
        result["answer"] = grounded
    return result

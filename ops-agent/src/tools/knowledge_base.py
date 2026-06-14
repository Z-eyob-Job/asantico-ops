"""knowledge_base tool: grounded retrieval over Asantico policy documents.

This is the knowledge RAG pipeline, collapsed into a single agent tool. In
production it calls the full LlamaIndex pipeline (vector index + learned
embedding). This self-contained version uses the same deterministic
hash-embedding idea so the demo answers real Asantico questions offline with
zero keys, and returns the source file for every snippet (grounding).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List, Tuple

KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "knowledge")
DIM = 256


def _vec(text: str) -> List[float]:
    v = [0.0] * DIM
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        d = hashlib.sha256(tok.encode()).digest()
        for i in range(0, len(d), 2):
            idx = (d[i] << 8 | d[i + 1]) % DIM
            v[idx] += 1.0 if d[i] & 1 == 0 else -1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _cos(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _load_chunks() -> List[Tuple[str, str]]:
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


def knowledge_base(query: str, top_k: int = 3) -> dict:
    """Retrieve the top-k most relevant policy snippets, with sources."""
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

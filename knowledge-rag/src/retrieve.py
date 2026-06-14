"""Stage 4-5 of the pipeline: retrieval and (optional) grounded generation.

Run a quick retrieval check from the project root:

    python -m src.retrieve "How is retrieval quality measured?"
"""

from __future__ import annotations

import os
import sys

from llama_index.core.retrievers import VectorIndexRetriever

from src.ingest import load_index

TOP_K = int(os.getenv("TOP_K", "4"))


def get_retriever(top_k: int = TOP_K) -> VectorIndexRetriever:
    """Return a vector retriever over the persisted index."""
    index = load_index()
    return VectorIndexRetriever(index=index, similarity_top_k=top_k)


def retrieve(query: str, top_k: int = TOP_K):
    """Return the top-k retrieved nodes for a query."""
    retriever = get_retriever(top_k)
    return retriever.retrieve(query)


def get_query_engine(top_k: int = TOP_K):
    """Return a grounded query engine (needs Settings.llm set to generate).

    With Settings.llm = None this still retrieves and assembles context; wire a
    real LLM (OpenAI, Anthropic, or local) to produce a cited natural-language
    answer. Generation is out of scope for the offline evaluation path.
    """
    index = load_index()
    return index.as_query_engine(similarity_top_k=top_k)


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "How is retrieval quality measured?"
    nodes = retrieve(q)
    print(f"Query: {q}\n")
    for rank, node in enumerate(nodes, start=1):
        source = node.node.metadata.get("file_name", "unknown")
        preview = node.node.get_content().strip().replace("\n", " ")[:110]
        print(f"  {rank}. score={node.score:.4f}  [{source}]  {preview}...")

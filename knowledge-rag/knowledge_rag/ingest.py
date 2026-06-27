"""Stage 1-3 of the pipeline: ingestion, chunking, embedding + indexing.

Run as a module from the project root:

    python -m knowledge_rag.ingest

This reads every file in ./corpus, splits it into chunks, embeds the chunks
with the configured backend, builds a VectorStoreIndex, and persists it to
./data/index so retrieval and evaluation can reload it without re-embedding.
"""

from __future__ import annotations

import os

from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter

from knowledge_rag.embeddings import get_embedding

CORPUS_DIR = os.getenv("CORPUS_DIR", "corpus")
INDEX_DIR = os.getenv("INDEX_DIR", "data/index")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "384"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))


def configure_settings() -> None:
    """Wire the global LlamaIndex settings used across the pipeline."""
    Settings.embed_model = get_embedding()
    Settings.node_parser = SentenceSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    # No generation LLM is needed for ingestion or retrieval evaluation.
    # MockLLM emits harmless stdout noise during query-engine calls only.
    Settings.llm = None


def build_index() -> VectorStoreIndex:
    """Ingest the corpus, chunk it, embed it, and persist the index."""
    configure_settings()

    # Stage 1 - Ingestion: filename is stamped into node metadata for later
    # filtering and failure analysis.
    documents = SimpleDirectoryReader(
        CORPUS_DIR, filename_as_id=True
    ).load_data()
    # Sort by source filename so node order (and thus tie-breaking in retrieval)
    # is identical on any machine, keeping metrics reproducible.
    documents.sort(key=lambda d: d.metadata.get("file_name", ""))

    # Stage 2 + 3 - Chunking, embedding, indexing happen inside from_documents
    # using the Settings configured above.
    index = VectorStoreIndex.from_documents(documents, show_progress=False)

    os.makedirs(INDEX_DIR, exist_ok=True)
    index.storage_context.persist(persist_dir=INDEX_DIR)
    print(
        f"Indexed {len(documents)} documents from {CORPUS_DIR!r} "
        f"(chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}) -> {INDEX_DIR!r}"
    )
    return index


def load_index() -> VectorStoreIndex:
    """Reload a persisted index, building it first if none exists."""
    configure_settings()
    if not os.path.exists(os.path.join(INDEX_DIR, "docstore.json")):
        return build_index()
    storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
    return load_index_from_storage(storage_context)


if __name__ == "__main__":
    build_index()

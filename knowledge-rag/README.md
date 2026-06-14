# Knowledge RAG Subsystem

A reproducible LlamaIndex retrieval pipeline over the Asantico knowledge base
(company policies, tax rules, billing workflow, client accounts, work-order
intake, service trades). It powers the `knowledge_base` tool in the operations
agent: ask a question in plain language and get a grounded answer with the source
document cited.

## Run it (offline, no keys, no API access)

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.ingest       # ingest, chunk, embed, persist the index
python -m src.evaluate     # hit rate + MRR, writes eval/evaluation_report.md
python -m src.retrieve "What is the Seattle sales tax rate?"
python -m src.agent "Does a client message need approval before sending?"
```

Run modules with `python -m src.<module>` from this folder.

## Pipeline

Five stages map directly onto the code. Ingestion reads `corpus/` with
`SimpleDirectoryReader` and stamps the filename into node metadata. Chunking uses
a `SentenceSplitter` at chunk size 384 with overlap 64. Embedding and indexing
build a `VectorStoreIndex` persisted to `data/index/`. Retrieval is a
`VectorIndexRetriever` at top_k 4. Generation exposes the query engine as a
`QueryEngineTool` to an `AgentWorkflow`.

## Embedding backend

The default is a deterministic hash embedding in `src/embeddings.py`: no keys, no
network, identical results on any machine. It ranks by token overlap rather than
meaning, so its scores are a reproducibility floor, not a quality ceiling.
Swapping to a learned backend is one line: set `EMBED_BACKEND=openai` (or
`huggingface`) in `.env`, install the matching package, and re-run ingest and
evaluate.

## Current results

On the ten-question fixed evaluation set with the offline hash backend: hit rate
0.900, MRR 0.850. One genuine miss (a query whose wording shares no tokens with
the source) and one soft miss are broken down query by query in
`eval/evaluation_report.md`, along with the iteration plan for raising both.

## Layout

```
corpus/                 the Asantico knowledge documents
src/embeddings.py       hash | openai | huggingface backends
src/ingest.py           ingestion, chunking, indexing, persistence
src/retrieve.py         retriever and grounded query engine
src/evaluate.py         hit rate + MRR + failure analysis + report writer
src/agent.py            AgentWorkflow wiring the RAG engine as a tool
eval/eval_questions.json  fixed evaluation set with ground truth
eval/evaluation_report.md generated metrics and failure analysis
docs/architecture-diagram.svg  pipeline diagram
```

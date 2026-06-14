"""Stage: retrieval evaluation. Computes hit rate and MRR over a fixed set.

Run from the project root:

    python -m src.evaluate

Writes a markdown report to eval/evaluation_report.md and prints a summary.

Metric definitions
-------------------
hit rate : fraction of queries for which at least one relevant file appears
           anywhere in the top-k retrieved results.
MRR      : mean reciprocal rank. For each query, find the rank of the FIRST
           retrieved chunk whose source file is relevant; the reciprocal rank
           is 1/rank (0 if no relevant file is retrieved). MRR is the mean of
           those reciprocal ranks across all queries.
"""

from __future__ import annotations

import json
import os
from datetime import date

from src.retrieve import get_retriever

EVAL_FILE = os.getenv("EVAL_FILE", "eval/eval_questions.json")
REPORT_FILE = os.getenv("REPORT_FILE", "eval/evaluation_report.md")
TOP_K = int(os.getenv("TOP_K", "4"))


def load_questions(path: str = EVAL_FILE) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["questions"]


def evaluate(top_k: int = TOP_K) -> dict:
    retriever = get_retriever(top_k)
    questions = load_questions()

    per_query = []
    hits = 0
    reciprocal_sum = 0.0

    for q in questions:
        relevant = set(q["relevant_files"])
        nodes = retriever.retrieve(q["query"])
        retrieved_files = [
            n.node.metadata.get("file_name", "unknown") for n in nodes
        ]

        # First rank (1-indexed) at which a relevant file appears.
        first_relevant_rank = None
        for rank, fname in enumerate(retrieved_files, start=1):
            if fname in relevant:
                first_relevant_rank = rank
                break

        hit = first_relevant_rank is not None
        rr = (1.0 / first_relevant_rank) if first_relevant_rank else 0.0
        hits += int(hit)
        reciprocal_sum += rr

        per_query.append(
            {
                "id": q["id"],
                "query": q["query"],
                "relevant_files": sorted(relevant),
                "retrieved_files": retrieved_files,
                "first_relevant_rank": first_relevant_rank,
                "hit": hit,
                "reciprocal_rank": round(rr, 4),
                "top_score": round(nodes[0].score, 4) if nodes else None,
            }
        )

    n = len(questions)
    summary = {
        "top_k": top_k,
        "num_queries": n,
        "hit_rate": round(hits / n, 4) if n else 0.0,
        "mrr": round(reciprocal_sum / n, 4) if n else 0.0,
        "embed_backend": os.getenv("EMBED_BACKEND", "hash"),
        "chunk_size": int(os.getenv("CHUNK_SIZE", "384")),
        "chunk_overlap": int(os.getenv("CHUNK_OVERLAP", "64")),
        "per_query": per_query,
    }
    return summary


def write_report(summary: dict, path: str = REPORT_FILE) -> None:
    lines = []
    lines.append("# Retrieval Evaluation Report")
    lines.append("")
    lines.append(f"Date: {date.today().isoformat()}  ")
    lines.append("Pipeline: LlamaIndex VectorStoreIndex over the Asantico knowledge base")
    lines.append("")
    lines.append("## Configuration")
    lines.append("")
    lines.append(
        f"Embedding backend was {summary['embed_backend']}, chunk size "
        f"{summary['chunk_size']} with overlap {summary['chunk_overlap']}, and "
        f"top_k {summary['top_k']}. The evaluation set holds "
        f"{summary['num_queries']} fixed queries, each labeled with the corpus "
        f"file that contains the answer."
    )
    lines.append("")
    lines.append("## Headline Metrics")
    lines.append("")
    lines.append(f"Hit rate: {summary['hit_rate']:.3f}  ")
    lines.append(f"MRR: {summary['mrr']:.3f}")
    lines.append("")
    lines.append("Hit rate is the fraction of queries where a relevant file "
                 "appears anywhere in the top-k. MRR averages the reciprocal of "
                 "the rank of the first relevant result, so it rewards putting "
                 "the right document at position one.")
    lines.append("")
    lines.append("## Per-Query Results")
    lines.append("")
    lines.append("| ID | First relevant rank | Reciprocal rank | Top score | Hit |")
    lines.append("|----|--------------------|-----------------|-----------|-----|")
    for r in summary["per_query"]:
        rank = r["first_relevant_rank"] if r["first_relevant_rank"] else "-"
        lines.append(
            f"| {r['id']} | {rank} | {r['reciprocal_rank']} | "
            f"{r['top_score']} | {'yes' if r['hit'] else 'NO'} |"
        )
    lines.append("")

    # Failure analysis: anything that did not land rank 1 is worth a note.
    misses = [r for r in summary["per_query"] if not r["hit"]]
    soft = [r for r in summary["per_query"] if r["hit"] and r["first_relevant_rank"] != 1]
    lines.append("## Failure Analysis")
    lines.append("")
    if not misses and not soft:
        lines.append(
            "No hard misses and no soft misses on this corpus: every query "
            "retrieved a relevant file at rank one. This is expected and is the "
            "central caveat of the result. The corpus is only four short, "
            "topically distinct documents and the hash embedding rewards exact "
            "token overlap, so the retrieval task is close to keyword matching. "
            "The headline numbers are therefore a ceiling, not a realistic "
            "estimate of production performance."
        )
        lines.append("")
        lines.append("Three failure modes are nonetheless designed for and will "
                     "surface once the corpus and embeddings grow:")
        lines.append("")
        lines.append("Low recall under lexical drift. The hash embedding cannot "
                     "match paraphrases that share no tokens with the source "
                     "(for example a query about cost or effort versus the doc "
                     "wording estimated time). A learned embedding is the fix.")
        lines.append("")
        lines.append("Metadata mismatch across documents. As the corpus grows, "
                     "added, several documents will discuss overlapping concepts "
                     "such as tax and billing, so file-level ground truth "
                     "will need document-type and section metadata to stay precise.")
        lines.append("")
        lines.append("Weak ranking on multi-relevant queries. Queries Q3 and Q10 "
                     "have two valid source files; with a larger corpus the "
                     "second relevant file will compete with near-duplicate "
                     "chunks, which is where a reranking step earns its place.")
    else:
        for r in misses:
            lines.append(
                f"Miss on {r['id']} ({r['query']}). Expected one of "
                f"{r['relevant_files']} but retrieved {r['retrieved_files']}. "
                f"Likely cause: lexical gap between the query and the source "
                f"wording under the hash embedding."
            )
            lines.append("")
        for r in soft:
            lines.append(
                f"Soft miss on {r['id']}: relevant file found but at rank "
                f"{r['first_relevant_rank']} rather than one, costing MRR. "
                f"Retrieved order was {r['retrieved_files']}."
            )
            lines.append("")
    lines.append("## Iteration Plan")
    lines.append("")
    lines.append("Diagnose, then adjust one lever at a time, then re-evaluate. "
                 "The ordered levers are: swap the hash embedding for a learned "
                 "backend, expand the corpus to weeks 1 through 6, tune chunk "
                 "size and overlap, add week and doc-type metadata filtering, "
                 "and finally add a reranking step measured by MRR lift.")
    lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    summary = evaluate()
    write_report(summary)
    print(
        f"backend={summary['embed_backend']} top_k={summary['top_k']} "
        f"n={summary['num_queries']}"
    )
    print(f"HIT RATE = {summary['hit_rate']:.3f}")
    print(f"MRR      = {summary['mrr']:.3f}")
    print(f"Report written to {REPORT_FILE}")

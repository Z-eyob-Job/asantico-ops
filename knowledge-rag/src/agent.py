"""Data-centric agent layer: wraps the RAG query engine as an agent tool.

This demonstrates the AgentWorkflow pattern. The retrieval pipeline is exposed to
an agent as a QueryEngineTool, so the agent decides when to consult the Asantico
knowledge base rather than answering from parametric memory. Running the agent end
to end needs a generation LLM configured in Settings.llm; without one this module
still constructs the tool and prints the wiring, which is what the offline path
exercises.

Run from the project root:

    python -m src.agent "What is the sales tax rate?"
"""

from __future__ import annotations

import os
import sys

from llama_index.core.tools import QueryEngineTool, ToolMetadata

from src.retrieve import get_query_engine

TOP_K = int(os.getenv("TOP_K", "4"))


def build_kb_tool() -> QueryEngineTool:
    """Expose the RAG query engine as a single retrieval tool for the agent."""
    query_engine = get_query_engine(TOP_K)
    return QueryEngineTool(
        query_engine=query_engine,
        metadata=ToolMetadata(
            name="asantico_kb",
            description=(
                "Answers questions about the Asantico knowledge base, including "
                "company policies, tax rules, billing workflow, client accounts, "
                "work-order intake, and service trades. Input is a natural "
                "language question."
            ),
        ),
    )


def build_agent():
    """Construct an AgentWorkflow over the knowledge-base tool.

    Requires Settings.llm to be a real generation model. Import is done lazily
    so the offline path (no LLM) can still build and inspect the tool.
    """
    from llama_index.core import Settings
    from llama_index.core.agent.workflow import AgentWorkflow

    if Settings.llm is None:
        raise RuntimeError(
            "AgentWorkflow needs a generation LLM. Set Settings.llm (OpenAI, "
            "Anthropic, or a local model) before building the agent."
        )

    tool = build_kb_tool()
    return AgentWorkflow.from_tools_or_functions(
        [tool],
        llm=Settings.llm,
        system_prompt=(
            "You are an operations assistant for Asantico. Always consult the "
            "asantico_kb tool before answering and ground every claim in the "
            "retrieved material. Cite the source file for each claim. If the "
            "knowledge base does not contain the answer, say so plainly."
        ),
    )


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "What is the sales tax rate?"
    tool = build_kb_tool()
    print("Built AgentWorkflow tool:")
    print(f"  name        = {tool.metadata.name}")
    print(f"  description = {tool.metadata.description[:80]}...")
    print()
    print("Offline mode: no generation LLM configured, so showing retrieval "
          "context the agent would ground on.\n")
    from src.retrieve import retrieve

    for rank, node in enumerate(retrieve(question), start=1):
        src = node.node.metadata.get("file_name", "unknown")
        preview = node.node.get_content().strip().replace("\n", " ")[:90]
        print(f"  {rank}. [{src}] {preview}...")

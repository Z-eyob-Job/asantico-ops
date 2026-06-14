"""Central tool registry. The agent can only call tools registered here, and
policy.py independently gates them by risk class. New capabilities are added in
one place."""

from __future__ import annotations

from src.tools import domain
from src.tools.knowledge_base import knowledge_base

REGISTRY = {
    "knowledge_base": knowledge_base,
    "query_jobs": domain.query_jobs,
    "compute_tax": domain.compute_tax,
    "triage_work_order": domain.triage_work_order,
    "generate_estimate": domain.generate_estimate,
    "generate_invoice": domain.generate_invoice,
    "draft_client_message": domain.draft_client_message,
    "finalize_invoice": domain.finalize_invoice,
    "send_client_message": domain.send_client_message,
}


def call(tool_name: str, **kwargs):
    if tool_name not in REGISTRY:
        raise KeyError(f"Unknown tool: {tool_name}")
    return REGISTRY[tool_name](**kwargs)

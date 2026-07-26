"""Central tool registry. The agent can only call tools registered here, and
policy.py independently gates them by risk class. New capabilities are added in
one place."""

from __future__ import annotations

import inspect
import logging

from src.tools import domain
from src.tools import chat as chat_tool
from src.tools import email_workorders, workorder
from src.tools.knowledge_base import knowledge_base

logger = logging.getLogger(__name__)

REGISTRY = {
    "knowledge_base": knowledge_base,
    "chat": chat_tool.chat,
    "load_work_order": workorder.load_work_order,
    "fetch_email_work_order": email_workorders.fetch_email_work_order,
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
    """Call a registered tool, dropping arguments its signature does not accept.

    LLM routers (cloud or local) sometimes attach extra keys ("rationale",
    "confidence", ...) inside the args object. A tool must never crash on that:
    unknown keys are logged and dropped, so every router backend can drive the
    same registry safely. The filter is signature-based, so adding a parameter
    to a tool automatically starts accepting it.
    """
    if tool_name not in REGISTRY:
        raise KeyError(f"Unknown tool: {tool_name}")
    fn = REGISTRY[tool_name]
    params = inspect.signature(fn).parameters
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        dropped = sorted(k for k in kwargs if k not in params)
        if dropped:
            logger.warning("Dropping unexpected args for %s: %s", tool_name, dropped)
            kwargs = {k: v for k, v in kwargs.items() if k in params}
    return fn(**kwargs)

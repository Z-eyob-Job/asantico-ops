"""Approval policy: the safety spine of the agent.

Every tool the agent can call is tagged with a risk class. Reads run freely.
Anything that spends money, finalizes a financial document, or sends a message to
a real client is GATED: the agent must get explicit human approval before the
action executes. This is the responsible-AI core of the project and the reason a
small business can trust the agent with real operations.
"""

from __future__ import annotations

from enum import Enum


class Risk(str, Enum):  # noqa: UP042
    READ = "read"        # no side effects, runs freely
    DRAFT = "draft"      # produces a document/message but does not send/finalize
    GATED = "gated"      # spends money, finalizes, or sends to a client: needs approval


# Tool name -> risk class. New tools MUST be registered here or they are denied.
TOOL_RISK = {
    "knowledge_base": Risk.READ,
    "load_work_order": Risk.READ,
    "fetch_email_work_order": Risk.READ,
    "query_jobs": Risk.READ,
    "compute_tax": Risk.READ,
    "triage_work_order": Risk.READ,
    "generate_estimate": Risk.DRAFT,
    "generate_invoice": Risk.DRAFT,
    "draft_client_message": Risk.DRAFT,
    "finalize_invoice": Risk.GATED,
    "send_client_message": Risk.GATED,
}


def risk_of(tool_name: str) -> Risk:
    if tool_name not in TOOL_RISK:
        raise PermissionError(f"Unregistered tool blocked by policy: {tool_name!r}")
    return TOOL_RISK[tool_name]


def needs_approval(tool_name: str) -> bool:
    """Gated actions require explicit human approval before they run."""
    return risk_of(tool_name) is Risk.GATED


def approval_prompt(tool_name: str, args: dict) -> str:
    """Human-readable confirmation message shown in the channel before acting."""
    return (
        f"Approval needed before I run '{tool_name}'.\n"
        f"Details: {args}\n"
        f"Reply 'approve' to proceed or 'cancel' to stop."
    )

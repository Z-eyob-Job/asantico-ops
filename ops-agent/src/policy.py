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
    """Human-readable review card shown in the channel before acting.

    No raw dicts: the operator reviews the document the way a person reads it -
    lines, money, recipient - then approves, cancels, or just says what to
    change (an edit supersedes the pending action)."""
    if tool_name == "finalize_invoice":
        items = args.get("line_items", []) or []
        sub = sum(li.get("amount", 0) for li in items)
        tax = round(sub * 0.1055, 2)
        lines = "\n".join(f"  {li.get('description','?'):<52} ${li.get('amount',0):>9,.2f}"
                          for li in items)
        head = f"{args.get('property','')} #{args.get('unit','')}".strip(" #")
        return ("Approval needed: FINALIZE INVOICE" + (f" for {head}" if head else "") + "\n"
                + (lines + "\n" if lines else "")
                + f"  {'Subtotal':<52} ${sub:>9,.2f}\n"
                + f"  {'Sales tax (10.55%)':<52} ${tax:>9,.2f}\n"
                + f"  {'TOTAL':<52} ${sub + tax:>9,.2f}\n"
                + "Reply 'approve' to finalize, 'cancel' to stop, or tell me what to change.")
    if tool_name == "send_client_message":
        return ("Approval needed: SEND CLIENT MESSAGE\n"
                f"  To: {args.get('to','?')}\n"
                f"  Subject: {args.get('subject','')}\n"
                f"  ---\n  {args.get('body','')}\n  ---\n"
                "Reply 'approve' to send, 'cancel' to stop, or tell me what to change.")
    pretty = ", ".join(f"{k}={v}" for k, v in args.items())
    return (f"Approval needed before I run '{tool_name}'. {pretty}\n"
            "Reply 'approve' to proceed or 'cancel' to stop.")

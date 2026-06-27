"""Router: turn a natural-language message into a tool call.

Production swaps in an LLM router (function calling over the registry). This
deterministic keyword router lets the whole agent run offline with no keys, so
the demo and tests are reproducible. The interface (message in, ToolCall out) is
identical, so swapping the LLM in does not change the loop or the policy layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    tool: str
    args: dict = field(default_factory=dict)
    rationale: str = ""
    notes: list = field(default_factory=list)  # assumptions worth surfacing/logging


def route(message: str) -> ToolCall:
    m = message.lower().strip()

    # Questions go to the knowledge base, even if they mention "invoice"/"tax".
    if m.endswith("?") or re.match(r"(what|how|why|when|who|where|which|is|are|does|can)\b", m):
        if not any(w in m for w in ("create", "make", "generate", "draft", "send")):
            return ToolCall("knowledge_base", {"query": message},
                            "Question phrasing detected; answering from the knowledge base.")

    # Finalize must be checked before the invoice branch, since "finalize the
    # invoice" also contains the word "invoice". Finalize is gated.
    if "finalize" in m:
        return ToolCall("finalize_invoice", {},
                        "User asked to finalize an invoice (gated).")

    # Approval / control words are handled by the loop, not the router.
    if any(w in m for w in ("invoice",)) and "send" not in m:
        prop, unit = _extract_property_unit(m)
        items, notes = _line_items_with_notes(m)
        return ToolCall("generate_invoice",
                        {"property": prop, "unit": unit, "line_items": items},
                        "User asked for an invoice.", notes)

    if "estimate" in m:
        prop, unit = _extract_property_unit(m)
        items, notes = _line_items_with_notes(m)
        return ToolCall("generate_estimate",
                        {"property": prop, "unit": unit, "line_items": items},
                        "User asked for an estimate.", notes)

    if any(w in m for w in ("leak", "broke", "broken", "not working", "log", "work order", "triage")):
        return ToolCall("triage_work_order", {"description": message},
                        "Looks like a new work order to triage.")

    if "tax" in m:
        amt = _extract_amount(m) or 0.0
        return ToolCall("compute_tax", {"subtotal": amt}, "Tax computation requested.")

    if any(w in m for w in ("send", "email", "message", "tell")) and "draft" not in m:
        mgr = "Saniya" if "saniya" in m else "Andrew" if "andrew" in m else "the manager"
        return ToolCall("send_client_message",
                        {"to": mgr, "subject": "Job update",
                         "body": "Work completed; documentation ready for review."},
                        "User asked to send a client message (gated).")

    if "draft" in m:
        mgr = "Saniya" if "saniya" in m else "Andrew" if "andrew" in m else "the manager"
        return ToolCall("draft_client_message",
                        {"manager": mgr, "subject": "Job update"},
                        "User asked to draft a client message.")

    if any(w in m for w in ("job", "status", "completed", "history")):
        prop, _ = _extract_property_unit(m)
        return ToolCall("query_jobs", {"property": prop}, "Job lookup.")

    # Default: treat as a knowledge-base question.
    return ToolCall("knowledge_base", {"query": message},
                    "No operational intent matched; answering from the knowledge base.")


def _extract_amount(m: str) -> float | None:
    # Prefer an explicit $ amount; fall back to a 'for N' / 'N dollars' amount,
    # so the unit number (e.g. "unit 208") is not mistaken for the price.
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", m)
    if not match:
        match = re.search(r"(?:for|of|\bat\b)\s*\$?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:dollars)?\b", m)
    return float(match.group(1)) if match else None


def _extract_property_unit(m: str):
    prop_match = re.search(r"\b(veer lofts|[a-z]+ lofts|[a-z]+ apartments|[a-z]+ residences)\b", m)
    unit_match = re.search(r"(?:unit|#|apt)\s*([0-9]+)", m)
    prop = prop_match.group(1).strip().title() if prop_match else "Unknown Property"
    unit = unit_match.group(1) if unit_match else "NA"
    return prop, unit


def _line_items_with_notes(m: str):
    """Return (line_items, notes). If no price is in the message, fall back to a
    default service-call amount and record a note so the assumption is surfaced
    to the operator and logged, rather than silently priced."""
    amt = _extract_amount(m)
    if amt is None:
        note = ("no price was found in the message, so a 150.00 service-call "
                "amount was assumed; confirm before finalizing.")
        return [{"description": "Service call", "amount": 150.0}], [note]
    return [{"description": "Service call", "amount": amt}], []

"""Domain tools.

In production each of these calls the real asantico-cli (the tax engine, the
ReportLab PDF generator, the triage agent). Here they are thin, functional stubs
that return structured results so the agent loop, routing, and approval policy
run end to end offline. The function signatures are the contract the build lanes
implement against the real CLI.

Asantico invariants enforced here (and in the real CLI): tax rate 10.55% on every
line item including labor, company name "Asantico" (never "Asantico LLC"), no
tenant names on documents, brief client messages with no dollar amounts.
"""

from __future__ import annotations

SEATTLE_TAX_RATE = 0.1055
COMPANY = "Asantico"


def compute_tax(subtotal: float, rate: float = SEATTLE_TAX_RATE) -> dict:
    tax = round(subtotal * rate, 2)
    return {"subtotal": round(subtotal, 2), "rate": rate, "tax": tax,
            "total": round(subtotal + tax, 2)}


def triage_work_order(description: str) -> dict:
    """Classify urgency and trade. Real version routes by urgency to a model."""
    text = description.lower()
    emergency = any(w in text for w in
                    ("leak", "flood", "gas", "no heat", "sparking", "fire", "burst"))
    trade = ("plumbing" if any(w in text for w in ("leak", "drain", "toilet", "pipe"))
             else "electrical" if any(w in text for w in ("outlet", "spark", "breaker"))
             else "general")
    return {"urgency": "emergency" if emergency else "routine",
            "trade": trade,
            "escalate": emergency,
            "note": "Escalated to human immediately." if emergency else "Queued for scheduling."}


def generate_estimate(property: str, unit: str, line_items: list[dict]) -> dict:
    subtotal = sum(li.get("amount", 0) for li in line_items)
    taxed = compute_tax(subtotal)
    return {"document": "estimate", "company": COMPANY, "property": property,
            "unit": unit, "line_items": line_items, **taxed,
            "status": "draft", "note": "Draft only. No tenant name included."}


def generate_invoice(property: str, unit: str, line_items: list[dict]) -> dict:
    est = generate_estimate(property, unit, line_items)
    est["document"] = "invoice"
    return est


def finalize_invoice(invoice_id: str) -> dict:
    """GATED: writes the final PDF and marks billable. Needs approval."""
    return {"invoice_id": invoice_id, "status": "finalized",
            "pdf": f"invoices/{invoice_id}.pdf"}


def draft_client_message(manager: str, subject: str) -> dict:
    """DRAFT: brief message, no dollar amounts, for human approval."""
    body = (f"Hi {manager}, the work has been completed and the documentation is "
            f"ready for your review. Please let me know if you need anything else. "
            f"Thank you, {COMPANY}.")
    return {"to": manager, "subject": subject, "body": body, "status": "draft"}


def send_client_message(to: str, subject: str, body: str) -> dict:
    """GATED: actually sends to a real client. Needs approval."""
    return {"to": to, "subject": subject, "status": "sent"}


def query_jobs(property: str | None = None) -> dict:
    """READ: look up job records. Stub returns a sample for the demo."""
    return {"property": property or "all",
            "jobs": [{"id": "WO-208", "property": "VEER LOFTS", "unit": "208",
                      "status": "completed", "trade": "plumbing"}]}

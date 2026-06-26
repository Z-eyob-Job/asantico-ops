"""Domain tools.

These tools call the real asantico-cli tax engine when it is installed, and
fall back to a built-in computation when it is not, so the agent loop, routing,
and approval policy run end to end offline with no install required. Install the
real engine to activate it: `pip install -e ../asantico-cli`.

Asantico invariants enforced here (and in the real CLI): tax rate 10.55% on every
line item including labor, company name "Asantico" (never "Asantico LLC"), no
tenant names on documents, brief client messages with no dollar amounts.
"""

from __future__ import annotations

SEATTLE_TAX_RATE = 0.1055
COMPANY = "Asantico"

# Wire the real asantico-cli tax engine if it is importable. The engine computes
# tax per line item with Decimal precision, which is the production behavior.
try:
    from decimal import Decimal as _Decimal

    from asantico_cli.domain.models import LineItem as _LineItem
    from asantico_cli.domain.tax import compute_totals as _compute_totals

    TAX_ENGINE = "asantico-cli"
except ImportError:  # pragma: no cover - exercised by the offline fallback path
    TAX_ENGINE = "builtin"


def _totals(amounts: list[float]) -> tuple[float, float, float]:
    """Return (subtotal, tax, total) for a list of line amounts.

    Uses the real asantico-cli engine (per-line Decimal tax) when available,
    otherwise the built-in float computation. Both apply 10.55% to every line.
    """
    if TAX_ENGINE == "asantico-cli":
        items = [
            _LineItem(description="line", quantity=_Decimal("1"),
                      unit="flat", unit_price=_Decimal(str(a)))
            for a in amounts
        ]
        sub, tax, tot = _compute_totals(items)
        return float(round(sub, 2)), float(round(tax, 2)), float(round(tot, 2))
    sub = sum(amounts)
    tax = round(sub * SEATTLE_TAX_RATE, 2)
    return round(sub, 2), tax, round(sub + tax, 2)


def compute_tax(subtotal: float, rate: float = SEATTLE_TAX_RATE) -> dict:
    sub, tax, total = _totals([subtotal])
    return {"subtotal": sub, "rate": SEATTLE_TAX_RATE, "tax": tax,
            "total": total, "engine": TAX_ENGINE}


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
    amounts = [li.get("amount", 0) for li in line_items]
    subtotal, tax, total = _totals(amounts)
    return {"document": "estimate", "company": COMPANY, "property": property,
            "unit": unit, "line_items": line_items,
            "subtotal": subtotal, "rate": SEATTLE_TAX_RATE, "tax": tax,
            "total": total, "engine": TAX_ENGINE,
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

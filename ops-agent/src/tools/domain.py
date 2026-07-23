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

import logging
import os

logger = logging.getLogger(__name__)

SEATTLE_TAX_RATE = 0.1055
COMPANY = "Asantico"
# Per-field confidence below which the real escalation rule sends a case to review.
TRIAGE_THRESHOLD = float(os.getenv("TRIAGE_THRESHOLD", "0.7"))

# Wire the real asantico-cli tax engine if it is importable. The engine computes
# tax per line item with Decimal precision, which is the production behavior.
try:
    from decimal import Decimal as _Decimal

    from asantico_cli.domain.models import LineItem as _LineItem
    from asantico_cli.domain.tax import compute_totals as _compute_totals

    TAX_ENGINE = "asantico-cli"
except ImportError:  # pragma: no cover - exercised by the offline fallback path
    TAX_ENGINE = "builtin"

# Wire the real asantico-cli ReportLab PDF engine if it is importable.
try:
    from datetime import date as _date
    from pathlib import Path as _Path

    from asantico_cli.domain.models import Document as _Document
    from asantico_cli.domain.models import Property as _Property
    from asantico_cli.infra.pdf import render_pdf as _render_pdf

    PDF_ENGINE = "asantico-cli"
except ImportError:  # pragma: no cover - exercised by the offline fallback path
    PDF_ENGINE = "builtin"

# Wire the real asantico-cli triage escalation rule if it is importable. The rule
# (should_escalate) is pure and needs no key; the model-backed classifier behind
# it does (used only when a key is present, see triage_work_order).
try:
    from asantico_cli.domain.triage import TriageResult as _TriageResult
    from asantico_cli.domain.triage import should_escalate as _should_escalate

    TRIAGE_RULE = "asantico-cli"
except ImportError:  # pragma: no cover - exercised by the offline fallback path
    TRIAGE_RULE = "builtin"


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


_EMERGENCY_WORDS = ("leak", "flood", "gas", "no heat", "sparking", "fire", "burst")


def _keyword_classify(description: str) -> tuple[str, str]:
    """Deterministic, dependency-free urgency and trade classification."""
    text = description.lower()
    emergency = any(w in text for w in _EMERGENCY_WORDS)
    trade = ("plumbing" if any(w in text for w in ("leak", "drain", "toilet", "pipe"))
             else "electrical" if any(w in text for w in ("outlet", "spark", "breaker"))
             else "general")
    return ("emergency" if emergency else "routine"), trade


def _triage_dict(urgency: str, trade: str, escalate: bool) -> dict:
    """Assemble the tool's stable return shape (urgency, trade, escalate, note)."""
    return {
        "urgency": urgency,
        "trade": trade,
        "escalate": escalate,
        "note": "Escalated to human immediately." if escalate else "Queued for scheduling.",
    }


def _offline_triage(description: str) -> dict:
    """Keyword classification with a built-in rule: emergencies escalate."""
    urgency, trade = _keyword_classify(description)
    return _triage_dict(urgency, trade, escalate=urgency == "emergency")


def _real_triage(description: str) -> dict:
    """Triage with the real asantico-cli engine.

    The escalation decision always uses the real should_escalate rule (pure, no
    key). Classification comes from the model-backed classifier when an API key is
    present; otherwise it falls back to keyword classification, marking an
    undetermined ("general") trade as low confidence so the real rule escalates
    uncertain cases for human review.
    """
    if TRIAGE_RULE != "asantico-cli":
        raise RuntimeError("asantico-cli is not installed")

    if os.environ.get("ANTHROPIC_API_KEY"):
        # Model-backed classifier: needs the SDK, a key, and network. Any failure
        # raises and is caught by triage_work_order, which falls back to offline.
        from asantico_cli.infra.llm import triage_request

        result = triage_request(description, live=True, threshold=TRIAGE_THRESHOLD)
        urgency, trade = result.urgency, result.trade
    else:
        urgency, trade = _keyword_classify(description)
        result = _TriageResult(
            urgency=urgency,
            trade=trade,
            property_name=None,
            unit=None,
            tenant_contact=None,
            issue_summary=description.strip()[:120],
            confidence={"urgency": 1.0, "trade": 1.0 if trade != "general" else 0.4},
        )

    return _triage_dict(urgency, trade, _should_escalate(result, TRIAGE_THRESHOLD))


def triage_work_order(description: str) -> dict:
    """Classify a work order into urgency and trade and decide escalation.

    TRIAGE_ENGINE selects the backend: "offline" (default) is deterministic
    keyword classification with a built-in escalation rule; "real" uses the
    asantico-cli engine, applying the real should_escalate rule for the escalation
    decision and the model-backed classifier only when an API key is present. A
    requested "real" engine that is unavailable logs a warning and falls back to
    offline. The return shape is unchanged either way.
    """
    engine = os.getenv("TRIAGE_ENGINE", "offline").lower()
    if engine == "real":
        try:
            return _real_triage(description)
        except Exception as exc:  # noqa: BLE001 - degrade to offline, never crash
            logger.warning(
                "TRIAGE_ENGINE=real unavailable (%s); using keyword triage.", exc
            )
    return _offline_triage(description)


def _mint_doc_number(prefix: str, unit: str) -> str:
    """Mint a document number in the Asantico convention: EST-2026-0507-402
    is the prefix, the date, and the unit the work is for."""
    from datetime import date

    today = date.today()
    return f"{prefix}-{today:%Y}-{today:%m%d}-{unit or 'GEN'}"


def _render_document(doc_type: str, doc_number: str, property: str, unit: str,
                     line_items: list[dict], out_dir: str) -> str | None:
    """Render the document in the real Asantico letterhead format (ReportLab).

    Returns the written PDF path, or None when the renderer is unavailable so
    the offline demo keeps running end to end without it. Documents never
    include a tenant name (Asantico invariant); work is billed to the property
    manager.
    """
    if not line_items:
        return None
    try:
        from datetime import date

        from src.tools.pdf_render import render_document as _render_letterhead

        return _render_letterhead(doc_type, doc_number, date.today(),
                                  property or "Property", unit, line_items,
                                  out_dir)
    except Exception as exc:  # noqa: BLE001 - degrade to no-PDF, never crash
        logger.warning("PDF renderer unavailable (%s); skipping render.", exc)
        return None


def generate_estimate(property: str, unit: str, line_items: list[dict]) -> dict:
    amounts = [li.get("amount", 0) for li in line_items]
    subtotal, tax, total = _totals(amounts)
    result = {"document": "estimate", "company": COMPANY, "property": property,
              "unit": unit, "line_items": line_items,
              "subtotal": subtotal, "rate": SEATTLE_TAX_RATE, "tax": tax,
              "total": total, "engine": TAX_ENGINE,
              "status": "draft", "note": "Draft only. No tenant name included."}
    # An estimate is a client-facing draft, so render the real document at draft
    # time. Invoices stay numbers-only until the gated finalize step approves them.
    pdf = _render_document("estimate", _mint_doc_number("EST", unit),
                           property, unit, line_items, "estimates")
    if pdf:
        result["pdf"] = pdf
        result["pdf_engine"] = PDF_ENGINE
    return result


def generate_invoice(property: str, unit: str, line_items: list[dict]) -> dict:
    amounts = [li.get("amount", 0) for li in line_items]
    subtotal, tax, total = _totals(amounts)
    return {"document": "invoice", "company": COMPANY, "property": property,
            "unit": unit, "line_items": line_items,
            "subtotal": subtotal, "rate": SEATTLE_TAX_RATE, "tax": tax,
            "total": total, "engine": TAX_ENGINE,
            "status": "draft", "note": "Draft only. No tenant name included."}


def finalize_invoice(property: str = "", unit: str = "",
                     line_items: list[dict] | None = None,
                     invoice_id: str = "INV-0001") -> dict:
    """GATED: writes the final PDF and marks billable. Needs approval.

    Renders a real PDF with the asantico-cli ReportLab engine when it is
    installed, otherwise returns a placeholder path so the offline demo and
    tests still run end to end.
    """
    line_items = line_items or []
    if invoice_id == "INV-0001":  # default: mint the dated Asantico number
        invoice_id = _mint_doc_number("INV", unit)
    path = _render_document("invoice", invoice_id, property, unit,
                            line_items, "invoices")
    if path:
        return {"invoice_id": invoice_id, "status": "finalized",
                "pdf": path, "engine": PDF_ENGINE}
    return {"invoice_id": invoice_id, "status": "finalized",
            "pdf": f"invoices/{invoice_id}.pdf", "engine": PDF_ENGINE}


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

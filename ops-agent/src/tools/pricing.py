"""Price proposal: turn an unpriced work order into a reviewable priced draft.

Real work orders often arrive with tasks but no prices - sometimes with only a
budget or NTE (not-to-exceed) amount. Refusing to draft until the operator
types every number wastes the agent. Instead, the agent PROPOSES prices, three
ways, in order of preference:

1. Budget allocation: when the work order carries a budget/NTE, allocate it
   across the tasks (weighted by the price book) so the subtotal meets it.
2. Local model: when Ollama is running, ask it for realistic Seattle handyman
   prices per task (JSON, validated, clamped to sane bounds).
3. Price book: a small built-in table of common maintenance tasks, learned
   from this business's own invoices; unknown tasks get the default rate.

Every proposed price is marked proposed=True and the draft carries a loud
note: these are suggestions for the operator to edit or accept. Nothing bills
without the approval gate, which is what makes guessing safe. Longer term the
price book is re-fit from the job ledger (logs/jobs.jsonl) - the agent learns
this operator's real pricing from every invoice they approve.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Seeded from Asantico's own past invoices (see examples in the cli repo).
PRICE_BOOK: list[tuple[str, float]] = [
    (r"bulb|light", 12.0),
    (r"outlet|switch|cover", 45.0),
    (r"drywall|patch", 120.0),
    (r"paint", 150.0),
    (r"toilet|flush", 60.0),
    (r"faucet|diverter|shower ?head", 65.0),
    (r"curtain|rod|shelf|mantel|mount|hang", 35.0),
    (r"deadbolt|lock|knob", 45.0),
    (r"batter|smoke|detector", 18.0),
    (r"clean|filter|air gap|wash", 40.0),
    (r"caulk|seal|grout", 45.0),
    (r"door|hinge|adjust", 55.0),
    (r"appliance|dishwasher|microwave|model number", 30.0),
    (r"haul|remove|junk", 90.0),
    (r"unit turn|turnover", 200.0),
]
DEFAULT_RATE = 60.0
MAX_LINE = 2000.0  # sanity clamp for model-proposed prices


def _book_price(description: str) -> float:
    d = description.lower()
    for pattern, price in PRICE_BOOK:
        if re.search(pattern, d):
            return price
    return DEFAULT_RATE


def _model_prices(tasks: list[str]) -> list[float] | None:
    """Ask the local model for per-task prices. None on any failure."""
    try:
        from src import local_llm

        if not local_llm.available():
            return None
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
        raw = local_llm.chat(
            "You price residential maintenance tasks for a Seattle handyman "
            "business. Reply ONLY with JSON: {\"prices\": [n1, n2, ...]} - one "
            "realistic flat price in USD per numbered task, materials and "
            "labor included, no explanations.",
            numbered, json_mode=True, timeout=45.0)
        prices = json.loads(raw).get("prices", [])
        if len(prices) != len(tasks):
            return None
        out = [round(min(max(float(p), 5.0), MAX_LINE), 2) for p in prices]
        return out
    except Exception as exc:  # noqa: BLE001 - proposal is best-effort
        logger.warning("Model price proposal unavailable (%s).", exc)
        return None


def propose_prices(tasks: list[str], budget: float | None = None) -> dict:
    """Return {'line_items': [...], 'method': str}. Items carry proposed=True."""
    tasks = [t for t in tasks if t.strip()][:25]
    if not tasks:
        return {"line_items": [], "method": "none"}

    prices = _model_prices(tasks)
    method = "local model" if prices else "price book"
    if prices is None:
        prices = [_book_price(t) for t in tasks]

    if budget and budget > 0:
        total = sum(prices) or 1.0
        scale = budget / total
        prices = [round(p * scale, 2) for p in prices]
        # settle rounding drift onto the last line so the subtotal is exact
        drift = round(budget - sum(prices), 2)
        prices[-1] = round(prices[-1] + drift, 2)
        method += f", allocated to the ${budget:,.2f} work-order budget"

    items = [{"description": t[:80], "amount": p, "proposed": True}
             for t, p in zip(tasks, prices)]
    return {"line_items": items, "method": method}

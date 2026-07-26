"""The job ledger: the agent's long-term memory of real work.

Every operationally meaningful outcome is appended as one JSON line to
logs/jobs.jsonl: a work order loaded, a document drafted, an invoice finalized,
a client message sent. This turns query_jobs from a stub into a real answer to
real questions - "what jobs did I do for Aravita", "how much did I bill this
month" - and gives the business a durable, greppable record that survives
restarts and lives next to the audit log.

Append-only JSONL by design: no database dependency, offline, human-readable,
and corruption of one line never loses the file.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

LEDGER_FILE = Path(os.getenv("JOB_LEDGER_FILE", "logs/jobs.jsonl"))


def record(kind: str, **fields) -> dict:
    """Append one ledger entry. kind: work_order_loaded | document_drafted |
    invoice_finalized | message_sent."""
    entry = {"ts": datetime.now(UTC).isoformat(), "kind": kind, **fields}
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    return entry


def _entries() -> list[dict]:
    if not LEDGER_FILE.exists():
        return []
    out = []
    for line in LEDGER_FILE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # one bad line never loses the ledger
    return out


def query(property: str | None = None, days: int | None = None) -> dict:
    """Summarize ledger entries, optionally filtered by property and recency."""
    entries = _entries()
    if property:
        needle = property.lower()
        entries = [e for e in entries
                   if needle in str(e.get("property", "")).lower()]
    if days:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        entries = [e for e in entries if e.get("ts", "") >= cutoff]

    finalized = [e for e in entries if e["kind"] == "invoice_finalized"]
    billed = round(sum(float(e.get("total", 0) or 0) for e in finalized), 2)
    jobs = [
        {"when": e["ts"][:10], "kind": e["kind"],
         "property": e.get("property", ""), "unit": e.get("unit", ""),
         "work_order": e.get("work_order", ""),
         "total": e.get("total"), "document": e.get("invoice_id") or e.get("pdf", "")}
        for e in entries
        if e["kind"] in ("work_order_loaded", "invoice_finalized", "message_sent")
    ]
    return {"count": len(jobs), "billed_total": billed,
            "invoices_finalized": len(finalized), "jobs": jobs[-15:],
            "property": property or "all", "days": days}

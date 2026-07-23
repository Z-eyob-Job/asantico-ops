"""Work-order ingestion: read an exported maintenance checklist and turn it into
a structured job the agent can act on.

Field workflow this solves: a work order arrives as an exported PDF (for example
a property-management app's "Maintenance Checklist" export). Instead of the
operator re-reading it and re-typing line items, the agent parses it - property,
unit, address, work-order number, tasks, and any per-task prices - and the loop
keeps it as the active job. "Make the estimate" then populates the letterhead
document from the work order for ANY property, and the client message draft
references the same job. Parsing is heuristic by design: every parsed value is
shown to the operator, and nothing client-facing leaves without the approval
gate, so a mis-parsed line is caught at review, not at the client.

Reads PDF text with pypdf (optional dependency, lazily imported) or plain .txt
files. Fully offline - no OCR service, no API.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALL_HINT = ("Reading PDF work orders needs pypdf. Install it once with: "
                "pip install pypdf")

_TS = re.compile(r"\d{2}/\d{2}/\d{4}")                      # photo caption timestamps
_DATELINE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}")       # "May 7, 2026, ..."
_PRICE = re.compile(r"^Price:\s*\$?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*$", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"^\+?\d{10,11}$")
_PROP_UNIT = re.compile(r"^(.+?)\s*#\s*([A-Za-z0-9-]+)\s*$")
_WO = re.compile(r"(?:WO|Work\s*Order)[\s#:-]*(\d[\d-]*)", re.I)
_PROGRESS = re.compile(r"^\d+\s*/\s*\d+$|Tasks?\s+Completed", re.I)


def _extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(INSTALL_HINT) from exc
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(errors="replace")


def parse_work_order(text: str, source_name: str = "") -> dict:
    """Parse checklist-export text into a structured job dict."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    prop, unit, address, contact_name, email, phone = "", "", "", "", "", ""
    tasks: list[dict] = []
    pending_price: float | None = None
    address_parts: list[str] = []
    name_parts: list[str] = []
    _ADDR_FRAG = re.compile(r"^([A-Z][a-z]+,?|[A-Z]{2},?|\d{5},?)$")

    for raw in lines:
        ln = raw.strip()
        if not prop:
            m = _PROP_UNIT.match(ln)
            if m and "checklist" not in ln.lower():
                prop, unit = m.group(1).strip().title(), m.group(2)
                continue
        if not email:
            m = _EMAIL.search(ln)
            if m:
                email = m.group(0)
                continue
        if not phone and _PHONE.match(ln.replace(" ", "")):
            phone = ln
            continue
        if prop and not email and re.match(r"^\d+\s", ln) and not _TS.search(ln) \
                and not address:
            address_parts.append(ln.rstrip(","))
            address = " ".join(dict.fromkeys(" ".join(address_parts).split()))
            continue
        if prop and not email and address and _ADDR_FRAG.match(ln):
            continue  # city/state/zip fragments wrapped onto their own lines
        if prop and not email and re.fullmatch(r"[A-Z][a-z]+", ln.rstrip()):
            name_parts.append(ln.strip())  # assignee name split across lines
            continue

        # Noise: headers, progress counters, dates, photo captions, bare names.
        low = ln.lower()
        if ("checklist" in low or _PROGRESS.search(ln) or _DATELINE.match(ln)
                or _TS.search(ln) or len(ln) < 4):
            continue
        m = _PRICE.match(ln)
        if m:
            # A price attaches to the NEXT task line in this export's layout;
            # if a task is never found it is dropped (and visible at review).
            pending_price = float(m.group(1))
            continue
        words = ln.split()
        if len(words) <= 3 and all(w[:1].isupper() for w in words) \
                and contact_name and ln.startswith(contact_name.split()[0]):
            continue  # repeated assignee caption under photos
        if not contact_name and len(words) == 2 and ln.istitle():
            contact_name = ln
            continue
        if len(words) == 1 and ln.isupper():
            continue  # username block like "EYOB"

        # Anything left is a task / note line.
        if tasks and tasks[-1]["description"].lower() == low:
            continue  # dedupe consecutive repeats
        task = {"description": ln[:100], "price": pending_price}
        pending_price = None
        tasks.append(task)

    if not contact_name and name_parts:
        contact_name = " ".join(name_parts[:2])

    wo = ""
    for source in (source_name, text):
        m = _WO.search(source)
        if m:
            wo = m.group(1)
            break

    priced = [t for t in tasks if t["price"] is not None]
    return {
        "ok": bool(tasks or prop),
        "source": source_name,
        "work_order": wo,
        "property": prop or "Unknown Property",
        "unit": unit or "NA",
        "address": address,
        "contact": {"name": contact_name, "email": email, "phone": phone},
        "tasks": tasks,
        "priced_items": [{"description": t["description"], "amount": t["price"]}
                         for t in priced],
        "task_count": len(tasks),
        "priced_count": len(priced),
    }


# Folders scanned when the operator says "find the latest work order" instead
# of giving a path. Override with WORKORDER_DIRS (colon-separated).
_SEARCH_DIRS = os.getenv("WORKORDER_DIRS",
                         "~/Downloads:~/Desktop:workorders/inbox").split(":")
_NAME_KEYWORDS = ("work order", "workorder", "checklist", "maintenance", "wo")


def find_work_order_file(query: str = "") -> Path | None:
    """Newest file in the search dirs that looks like a work order.

    A file qualifies when its name contains a work-order keyword, or the
    operator's query (e.g. a property name). Newest modification time wins, so
    "the work order I just exported" is the natural match.
    """
    needle = query.lower().strip()
    candidates: list[Path] = []
    for d in _SEARCH_DIRS:
        folder = Path(d).expanduser()
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            if f.suffix.lower() not in (".pdf", ".txt") or not f.is_file():
                continue
            name = f.name.lower()
            if any(k in name for k in _NAME_KEYWORDS) or (needle and needle in name):
                candidates.append(f)
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


def load_work_order(path: str = "", query: str = "") -> dict:
    """READ: parse a work-order file (.pdf or .txt) into the active job.

    With no path (or "latest"), searches Downloads/Desktop/workorders-inbox for
    the newest work-order-looking file, so the operator never types a path.
    """
    raw = path.strip().strip("'\"")
    if raw and raw.lower() not in ("latest", "newest", "downloads", "auto"):
        p = Path(raw).expanduser()
    else:
        found = find_work_order_file(query)
        if found is None:
            dirs = ", ".join(_SEARCH_DIRS)
            return {"ok": False, "error": (
                "No work-order file found in " + dirs + ". Export the "
                "checklist there, or give me the file directly: workorder <path>.")}
        p = found
    if not p.exists():
        return {"ok": False, "error": f"Work order file not found: {p}"}
    try:
        text = _extract_text(p)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - degrade with a message, never crash
        return {"ok": False, "error": f"Could not read {p.name}: {exc}"}
    job = parse_work_order(text, source_name=p.name)
    logger.info("Parsed work order %s: %s #%s, %d tasks (%d priced)",
                p.name, job["property"], job["unit"], job["task_count"],
                job["priced_count"])
    return job

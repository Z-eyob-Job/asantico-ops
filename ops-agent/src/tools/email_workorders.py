"""Fetch work orders from the operator's email inbox.

The other half of work-order ingestion (src/tools/workorder.py reads local
files): "check email for work orders" logs into the operator's inbox over IMAP,
scans recent messages for a work-order attachment (a checklist export PDF),
downloads the newest one into workorders/inbox/, and parses it with the same
parser. The agent loop then treats it as the active job, exactly as if the file
had been loaded locally - property, unit, tasks, prices, and the sender becomes
the default recipient for drafts (the property manager who emailed the work
order is usually the person to reply to).

Standard library only (imaplib + email), preserving the no-new-dependency rule
for channels and transports. Credentials come from the environment and are
never logged:

    EMAIL_IMAP_HOST  (default imap.gmail.com)
    EMAIL_USER       (the inbox address)
    EMAIL_PASS       (an app password - for Gmail: Google Account > Security >
                      2-Step Verification > App passwords)

Without credentials the tool degrades to a one-line setup hint, never a crash.
This is a READ tool: fetching and parsing an email cannot spend money or
contact a client; anything that can still stops at the approval gate.
"""

from __future__ import annotations

import email
import email.header
import imaplib
import logging
import os
import re
import socket
from pathlib import Path

from src.tools.workorder import parse_work_order

logger = logging.getLogger(__name__)

INBOX_DIR = Path("workorders/inbox")
# An attachment or subject matching any of these looks like a work order.
_KEYWORDS = ("work order", "workorder", "checklist", "maintenance", "wo", "turn")
_SEARCH_LIMIT = 25  # newest N messages scanned per check


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _looks_like_work_order(filename: str, subject: str) -> bool:
    hay = f"{filename} {subject}".lower()
    return filename.lower().endswith(".pdf") and any(k in hay for k in _KEYWORDS)


def fetch_email_work_order(query: str = "") -> dict:
    """READ: scan the inbox for the newest work-order attachment and parse it.

    Optional query narrows the match (e.g. a property name that must appear in
    the subject or filename).
    """
    host = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
    user = os.getenv("EMAIL_USER", "")
    password = os.getenv("EMAIL_PASS", "")
    if not user or not password:
        return {"ok": False, "error": (
            "Email is not configured. Set EMAIL_USER and EMAIL_PASS (an app "
            "password) in ops-agent/.env - for Gmail create one under Google "
            "Account > Security > 2-Step Verification > App passwords.")}

    socket.setdefaulttimeout(20)
    try:
        imap = imaplib.IMAP4_SSL(host)
        imap.login(user, password)
        imap.select("INBOX", readonly=True)
        _status, data = imap.search(None, "ALL")
        ids = data[0].split()
        candidates = ids[-_SEARCH_LIMIT:][::-1]  # newest first

        needle = query.lower().strip()
        for msg_id in candidates:
            _status, msg_data = imap.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _decode(msg.get("Subject"))
            sender = _decode(msg.get("From"))
            for part in msg.walk():
                filename = _decode(part.get_filename())
                if not filename or not _looks_like_work_order(filename, subject):
                    continue
                if needle and needle not in f"{filename} {subject}".lower():
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                INBOX_DIR.mkdir(parents=True, exist_ok=True)
                safe_name = re.sub(r"[^\w.\- ]", "_", filename)
                saved = INBOX_DIR / safe_name
                saved.write_bytes(payload)
                imap.logout()

                from src.tools.workorder import load_work_order

                job = load_work_order(str(saved))
                job["email_from"] = sender
                job["email_subject"] = subject
                job["email_date"] = _decode(msg.get("Date"))
                name_match = re.match(r'\s*"?([^"<]+?)"?\s*<', sender)
                job["email_from_name"] = (name_match.group(1).strip()
                                          if name_match else sender)
                logger.info("Fetched work order %r from %r", filename, sender)
                return job
        imap.logout()
        return {"ok": False, "error": (
            f"No work-order attachment found in the newest {_SEARCH_LIMIT} "
            "messages" + (f" matching '{query}'" if query else "") + ".")}
    except Exception as exc:  # noqa: BLE001 - degrade with a message, never crash
        logger.warning("Email work-order fetch failed: %s", exc)
        return {"ok": False, "error": f"Could not check email: {exc}"}

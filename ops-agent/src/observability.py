"""Observability: structured, append-only event logging for the agent.

Every meaningful step the agent takes emits one JSON line: the inbound message,
the routing decision, the policy verdict, an approval request, an approval grant
or denial, a tool execution, and the final result. Structured logs make the
agent auditable, which matters when it touches money and clients, and they double
as the demo evidence for the prototype kickoff.

Each event carries a correlation id (the conversation id) and a UTC timestamp, so
a full request can be reconstructed from the log after the fact.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime

LOG_FILE = os.getenv("AGENT_LOG_FILE", "logs/agent.jsonl")
LOG_TO_STDERR = os.getenv("AGENT_LOG_STDERR", "1") == "1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def log_event(event: str, conv_id: str, trace_id: str, **fields) -> dict:
    """Emit one structured event. Returns the record for convenience/testing."""
    record = {
        "ts": _now(),
        "trace_id": trace_id,
        "conv_id": conv_id,
        "event": event,
        **fields,
    }
    line = json.dumps(record, default=str)

    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    if LOG_TO_STDERR:
        # stderr so it never pollutes a channel's stdout reply stream.
        print(line, file=sys.stderr)

    return record

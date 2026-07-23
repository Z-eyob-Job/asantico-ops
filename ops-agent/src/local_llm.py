"""Local LLM client (Ollama): smart behavior with no cloud API and no key.

Field constraint drives this design: job sites often have no connection, and
the operator does not want deterministic canned responses. Ollama runs a small
model (default qwen2.5:3b, ~2 GB) entirely on the local machine - Apple Silicon
GPU via Metal, or any CPU - over a localhost HTTP endpoint. After the one-time
`ollama pull`, everything works with zero connectivity and zero keys.

Used in two places, both with the same degrade-gracefully contract as every
other optional upgrade in this repo:

- ROUTER_BACKEND=local: the local model routes free-form messages to tools
  (src/agent/router.py local_route). Any failure - Ollama not running, bad
  JSON, unknown tool - falls back to the keyword router. The policy gate sits
  after routing either way, so a misrouted gated action still stops for
  approval.
- Client message drafts: when Ollama is up, drafts are written by the local
  model with the job context, then sanitized against the business rules (no
  dollar amounts, no em dashes) and template-fallback on any violation. Drafts
  are still drafts: nothing is sent without the gate.

Standard library only (urllib). Configuration:
    OLLAMA_URL   default http://localhost:11434
    LOCAL_MODEL  default qwen2.5:3b   (try llama3.2:3b or qwen2.5:7b too)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "qwen2.5:3b")

_available: bool | None = None  # probed once per process


def available() -> bool:
    """True when an Ollama server answers on localhost. Cached per process."""
    global _available
    if _available is None:
        try:
            with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1.5):
                _available = True
        except (urllib.error.URLError, OSError):
            _available = False
    return _available


def chat(system: str, user: str, json_mode: bool = False,
         timeout: float = 60.0) -> str:
    """One chat turn against the local model. Raises on any failure so callers
    can fall back; never returns a half-parsed result silently."""
    body = {
        "model": LOCAL_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    return payload["message"]["content"]

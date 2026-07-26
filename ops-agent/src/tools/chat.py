"""Conversational replies: the agent as a colleague, not a command parser.

Greetings, thanks, "what can you do", and general back-and-forth route here
instead of the knowledge base, so the agent answers like a person. When a local
Ollama model is running the reply is generated with the conversation context
(same zero-cloud, zero-key setup as the router); otherwise a friendly canned
reply keeps the offline demo working.

READ risk: talking can never spend money or contact a client.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PERSONA = (
    "You are the Asantico operations assistant, a warm, brief, practical "
    "colleague for a Seattle property-maintenance operator. Reply in 1-3 short "
    "sentences, in the operator's language. Never invent prices or job facts. "
    "You can: load work orders (from email, Downloads, or a file), draft "
    "estimates and invoices as real letterhead PDFs, edit lines in plain words, "
    "and draft client messages - and anything that bills money or reaches a "
    "client always stops for the operator's approval. No em dashes."
)

_FALLBACK = ("Hi! I can pull a work order (say 'check email for work orders' or "
             "'find the latest work order'), draft the estimate or invoice as a "
             "real PDF, take edits in plain words, and draft client messages. "
             "Anything that bills or reaches a client waits for your approval.")


def chat(message: str, context: str = "") -> dict:
    """READ: converse. Local-model reply when available, canned otherwise."""
    reply = _FALLBACK
    try:
        from src import local_llm

        if local_llm.available():
            user = message if not context else f"(context: {context})\n{message}"
            out = local_llm.chat(_PERSONA, user, timeout=30.0).strip()
            if out:
                reply = out.replace("—", "-")
    except Exception as exc:  # noqa: BLE001 - degrade to the canned reply
        logger.warning("Chat generation unavailable (%s); using fallback.", exc)
    return {"reply": reply}

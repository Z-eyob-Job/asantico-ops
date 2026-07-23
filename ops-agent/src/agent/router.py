"""Router: turn a natural-language message into a tool call.

Two interchangeable routers sit behind one interface, selected by the
``ROUTER_BACKEND`` environment variable:

- ``keyword`` (default): a deterministic keyword router. It lets the whole agent
  run offline with no keys, so the demo and tests are reproducible.
- ``llm``: an Anthropic function-calling router over the same tool registry. If
  ``llm`` is selected but no ``ANTHROPIC_API_KEY`` is present, the SDK is missing,
  or the call fails, the router logs a warning and falls back to keyword routing.

Both return the same ``ToolCall(tool, args, rationale, notes)`` shape, so the
agent loop and the policy gate never change. Whichever router runs, the policy
gate still stops every gated action, so a misrouted gated call is still safe.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

from src import llm

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    tool: str
    args: dict = field(default_factory=dict)
    rationale: str = ""
    notes: list = field(default_factory=list)  # assumptions worth surfacing/logging


def route(message: str) -> ToolCall:
    """Route a message to a tool using the configured backend.

    ROUTER_BACKEND=llm uses the Anthropic function-calling router; anything else
    (default) uses the keyword router. A requested LLM router that cannot run
    degrades to the keyword router rather than failing.
    """
    backend = os.getenv("ROUTER_BACKEND", "keyword").lower()
    if backend == "llm":
        try:
            return llm_route(message)
        except Exception as exc:  # noqa: BLE001 - any failure must degrade, not crash
            logger.warning(
                "ROUTER_BACKEND=llm unavailable (%s); falling back to keyword router.",
                exc,
            )
    if backend in ("local", "ollama"):
        try:
            return local_route(message)
        except Exception as exc:  # noqa: BLE001 - any failure must degrade, not crash
            logger.warning(
                "ROUTER_BACKEND=local unavailable (%s); falling back to keyword router.",
                exc,
            )
    return keyword_route(message)


_LOCAL_ROUTER_SYSTEM = """You route one operator message for a Seattle \
property-maintenance business to exactly one tool. Reply with ONLY a JSON \
object: {"tool": <name>, "args": {...}, "rationale": <short string>}.

Tools and their args:
- knowledge_base {"query": str}: questions about policy, tax, procedures.
- load_work_order {"path": str, "query": str}: load/find a work-order file. \
Empty path means search Downloads for the newest one; query filters by name.
- fetch_email_work_order {"query": str}: pull the newest work-order attachment \
from email.
- triage_work_order {"description": str}: classify a new problem report.
- compute_tax {"subtotal": number}
- generate_estimate {"property": str, "unit": str, "line_items": [{"description": str, "amount": number}]}: \
new estimate. To EDIT the current draft use {"edit": {"add": {"description": str, "amount": number}}} \
and/or {"edit": {"target_subtotal": number}} instead.
- generate_invoice: same args as generate_estimate.
- draft_client_message {"manager": str, "subject": str}
- send_client_message {"to": str, "subject": str, "body": str}: GATED.
- finalize_invoice {}: GATED.
- query_jobs {"property": str}

Rules: pick the single best tool. "tool" MUST be one of the names above, \
never null. Omit args you cannot infer (use "" or []). Never invent prices. \
If the message edits an existing draft (add lines, change the total), use the \
edit payload; "add" may be a LIST for compound requests. If it is a question, \
use knowledge_base.

Examples:
"add 100 and add materials which is $30" -> {"tool": "generate_estimate", \
"args": {"edit": {"add": [{"description": "Additional charge", "amount": 100}, \
{"description": "Materials", "amount": 30}]}}, "rationale": "two line items added"}
"the tenant says the heater is dead" -> {"tool": "triage_work_order", \
"args": {"description": "the tenant says the heater is dead"}, "rationale": \
"new problem report"}"""


def local_route(message: str) -> ToolCall:
    """Route with a local Ollama model (no cloud, no key). Raises on any
    problem so route() falls back to the keyword router."""
    from src import local_llm
    from src.tools import registry

    if not local_llm.available():
        raise RuntimeError("Ollama is not running on localhost")
    tool, args, data = None, {}, {}
    for attempt in (1, 2):  # one retry: small local models misfire occasionally
        raw = local_llm.chat(_LOCAL_ROUTER_SYSTEM, message, json_mode=True)
        data = json.loads(raw)
        tool = data.get("tool")
        args = data.get("args") or {}
        if tool in registry.REGISTRY and isinstance(args, dict):
            break
    if tool not in registry.REGISTRY or not isinstance(args, dict):
        raise ValueError(f"local router proposed unknown tool: {tool!r}")
    return ToolCall(tool, args, data.get("rationale", "local model routing"),
                    ["routed by local model (" + os.getenv("LOCAL_MODEL", "qwen2.5:3b") + ")"])


def keyword_route(message: str) -> ToolCall:
    m = message.lower().strip()

    # Work-order ingestion comes first: "workorder <file>" (also "load work
    # order <file>"). The path keeps the original casing from the raw message.
    for prefix in ("workorder ", "load work order "):
        if m.startswith(prefix):
            path = message.strip()[len(prefix):].strip()
            return ToolCall("load_work_order", {"path": path},
                            "Operator supplied a work-order file to ingest.")

    # "find the latest work order" (no path): search Downloads/Desktop for the
    # newest work-order-looking file. Checked before triage's "work order" rule.
    if "work order" in m and "email" not in m \
            and any(w in m for w in ("find", "load", "latest", "newest", "download", "search", "grab", "pull")):
        needle = ""
        nm = re.search(r"(?:for|about)\s+([a-z0-9 ]{3,30})$", m)
        if nm:
            needle = nm.group(1).strip()
        return ToolCall("load_work_order", {"path": "", "query": needle},
                        "Searching local folders for the newest work order.")

    # "check email for work orders" / "get the work order from email": scan the
    # inbox for the newest checklist attachment. Checked before the send rule
    # so the word "email" here never routes to a gated send.
    if "email" in m and any(w in m for w in ("check", "fetch", "get", "look", "read", "scan", "find")):
        needle = ""
        nm = re.search(r"(?:for|about)\s+([a-z0-9 ]{3,30})$", m)
        if nm and "work order" not in nm.group(1):
            needle = nm.group(1).strip()
        return ToolCall("fetch_email_work_order", {"query": needle},
                        "Operator asked to pull a work order from email.")

    # Questions go to the knowledge base, even if they mention "invoice"/"tax".
    if m.endswith("?") or re.match(r"(what|how|why|when|who|where|which|is|are|does|can)\b", m):
        if not any(w in m for w in ("create", "make", "generate", "draft", "send")):
            return ToolCall("knowledge_base", {"query": message},
                            "Question phrasing detected; answering from the knowledge base.")

    # Edits to the current draft: "add materials which is 30", "add labor for
    # 450", "make the total price 300". Routed as a re-generate with an edit
    # payload; the loop merges it with the draft the operator is looking at.
    edit: dict = {}
    adds = []
    for am in re.finditer(r"\badd (?:a |an |some |another )?([a-z][a-z /-]{1,40}?)(?:\s*,?\s*which is|\s+for|\s+at|\s+of|:)?\s*\$?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:dollars)?\b", m):
        desc = am.group(1).strip()
        # strip filler so "another price on the materials" becomes "materials"
        desc = re.sub(r"^(price on the |price for the |price on |price for |the )", "", desc).strip()
        adds.append({"description": (desc or "Additional charge").title(),
                     "amount": float(am.group(2))})
    for am in re.finditer(r"\badd\s+\$?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:dollars)?(?=\s|,|$|\band\b)", m):
        amt = float(am.group(1))
        if not any(a["amount"] == amt for a in adds):
            adds.append({"description": "Additional charge", "amount": amt})
    if adds:
        edit["add"] = adds
    tot_m = re.search(r"\b(?:make|set|change)\b.{0,30}?\b(?:total|price|subtotal)\b.{0,15}?\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", m)
    if tot_m:
        edit["target_subtotal"] = float(tot_m.group(1))
    if edit:
        return ToolCall("generate_estimate", {"edit": edit},
                        "Operator edited the current draft.")

    # Finalize must be checked before the invoice branch, since "finalize the
    # invoice" also contains the word "invoice". Finalize is gated.
    if "finalize" in m:
        return ToolCall("finalize_invoice", {},
                        "User asked to finalize an invoice (gated).")

    # Approval / control words are handled by the loop, not the router.
    if any(w in m for w in ("invoice",)) and "send" not in m:
        prop, unit = _extract_property_unit(m)
        items, notes = _line_items_with_notes(m)
        return ToolCall("generate_invoice",
                        {"property": prop, "unit": unit, "line_items": items},
                        "User asked for an invoice.", notes)

    if "estimate" in m:
        prop, unit = _extract_property_unit(m)
        items, notes = _line_items_with_notes(m)
        return ToolCall("generate_estimate",
                        {"property": prop, "unit": unit, "line_items": items},
                        "User asked for an estimate.", notes)

    if any(w in m for w in ("leak", "broke", "broken", "not working", "log", "work order", "triage")):
        return ToolCall("triage_work_order", {"description": message},
                        "Looks like a new work order to triage.")

    if "tax" in m:
        amt = _extract_amount(m) or 0.0
        return ToolCall("compute_tax", {"subtotal": amt}, "Tax computation requested.")

    if any(w in m for w in ("send", "email", "message", "tell")) and "draft" not in m:
        mgr = "Saniya" if "saniya" in m else "Andrew" if "andrew" in m else "the manager"
        return ToolCall("send_client_message",
                        {"to": mgr, "subject": "Job update",
                         "body": "Work completed; documentation ready for review."},
                        "User asked to send a client message (gated).")

    if "draft" in m:
        mgr = "Saniya" if "saniya" in m else "Andrew" if "andrew" in m else "the manager"
        return ToolCall("draft_client_message",
                        {"manager": mgr, "subject": "Job update"},
                        "User asked to draft a client message.")

    if any(w in m for w in ("job", "status", "completed", "history")):
        prop, _ = _extract_property_unit(m)
        return ToolCall("query_jobs", {"property": prop}, "Job lookup.")

    # Default: treat as a knowledge-base question.
    return ToolCall("knowledge_base", {"query": message},
                    "No operational intent matched; answering from the knowledge base.")


def _extract_amount(m: str) -> float | None:
    # Prefer an explicit $ amount; fall back to a 'for N' / 'N dollars' amount,
    # so the unit number (e.g. "unit 208") is not mistaken for the price.
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", m)
    if not match:
        match = re.search(r"(?:for|of|\bat\b)\s*\$?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:dollars)?\b", m)
    return float(match.group(1)) if match else None


def _extract_property_unit(m: str):
    prop_match = re.search(r"\b(veer lofts|[a-z]+ lofts|[a-z]+ apartments|[a-z]+ residences)\b", m)
    unit_match = re.search(r"(?:unit|#|apt)\s*([0-9]+)", m)
    prop = prop_match.group(1).strip().title() if prop_match else "Unknown Property"
    unit = unit_match.group(1) if unit_match else "NA"
    return prop, unit


def _line_items_with_notes(m: str):
    """Return (line_items, notes). If no price is in the message, fall back to a
    default service-call amount and record a note so the assumption is surfaced
    to the operator and logged, rather than silently priced."""
    amt = _extract_amount(m)
    if amt is None:
        note = ("no price was found in the message, so a 150.00 service-call "
                "amount was assumed; confirm before finalizing.")
        return [{"description": "Service call", "amount": 150.0}], [note]
    return [{"description": "Service call", "amount": amt}], []


# --------------------------------------------------------------------------- #
# LLM router: Anthropic function calling over the same tool registry.
# --------------------------------------------------------------------------- #
# One tool definition per registered tool. The model picks exactly one (tool
# choice is forced), which keeps routing inside the policy-governed registry.
_LINE_ITEMS_SCHEMA = {
    "type": "array",
    "description": "Line items, each an amount in dollars with a description.",
    "items": {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "amount": {"type": "number"},
        },
    },
}

_LLM_TOOLS = [
    {
        "name": "knowledge_base",
        "description": (
            "Answer a policy, tax, billing, or company-rules question from the "
            "grounded Asantico knowledge base. Use for questions, even if they "
            "mention an invoice or tax, when the user is asking rather than "
            "requesting a document or a send."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "query_jobs",
        "description": "Look up existing job or work-order records, optionally for one property.",
        "input_schema": {
            "type": "object",
            "properties": {"property": {"type": "string"}},
        },
    },
    {
        "name": "compute_tax",
        "description": "Compute Seattle sales tax (10.55%) on a subtotal amount.",
        "input_schema": {
            "type": "object",
            "properties": {"subtotal": {"type": "number"}},
        },
    },
    {
        "name": "triage_work_order",
        "description": (
            "Triage a new maintenance request into urgency and trade. Use when "
            "the user reports a problem (a leak, something broken or not working)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"description": {"type": "string"}},
            "required": ["description"],
        },
    },
    {
        "name": "generate_estimate",
        "description": "Draft (not send) a priced estimate for a property and unit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "property": {"type": "string"},
                "unit": {"type": "string"},
                "line_items": _LINE_ITEMS_SCHEMA,
            },
        },
    },
    {
        "name": "generate_invoice",
        "description": "Draft (not finalize) a priced invoice for a property and unit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "property": {"type": "string"},
                "unit": {"type": "string"},
                "line_items": _LINE_ITEMS_SCHEMA,
            },
        },
    },
    {
        "name": "draft_client_message",
        "description": (
            "Draft (do NOT send) a brief client message for a manager to review. "
            "Use only when the operator explicitly asks to draft or write a message "
            "without sending it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "manager": {"type": "string"},
                "subject": {"type": "string"},
            },
        },
    },
    {
        "name": "finalize_invoice",
        "description": (
            "GATED. Finalize a drafted invoice into a billable PDF. Requires human "
            "approval before it runs."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "send_client_message",
        "description": (
            "GATED. Send a message or update to a client. The property managers "
            "(for example Saniya and Andrew) are the clients, so 'send an update to "
            "Saniya' is a client send. Choose this whenever the operator asks to "
            "send, email, or deliver a message. Requires human approval before it runs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
]

_LLM_SYSTEM = (
    "You are the router for Asantico's operations agent. Choose exactly one tool "
    "that best handles the operator's message. Route plain questions to "
    "knowledge_base. The property managers (for example Saniya and Andrew) are the "
    "clients: when the operator asks to send, email, or deliver a message or update "
    "to a manager or client, choose send_client_message. Choose draft_client_message "
    "only when the operator explicitly asks to draft or write a message without "
    "sending it. Use generate_estimate or generate_invoice to draft documents and "
    "finalize_invoice to finalize one. Selecting a gated tool is fine; a human "
    "approves before it runs, so never avoid the correct tool out of caution."
)


def _manager_from(m: str) -> str:
    return "Saniya" if "saniya" in m else "Andrew" if "andrew" in m else "the manager"


def _complete_args(tool: str, message: str, llm_args: dict) -> tuple[dict, list]:
    """Backfill required arguments the model may have omitted, reusing the same
    deterministic extractors as the keyword router. This guarantees the selected
    tool is executable and that an assumed price is still surfaced as a note."""
    m = message.lower().strip()
    args = dict(llm_args or {})
    notes: list = []

    if tool == "knowledge_base":
        args.setdefault("query", message)
    elif tool == "triage_work_order":
        args.setdefault("description", message)
    elif tool == "compute_tax":
        args.setdefault("subtotal", _extract_amount(m) or 0.0)
    elif tool in ("generate_estimate", "generate_invoice"):
        prop, unit = _extract_property_unit(m)
        args.setdefault("property", prop)
        args.setdefault("unit", unit)
        if not args.get("line_items"):
            items, notes = _line_items_with_notes(m)
            args["line_items"] = items
    elif tool == "draft_client_message":
        args.setdefault("manager", _manager_from(m))
        args.setdefault("subject", "Job update")
    elif tool == "send_client_message":
        args.setdefault("to", _manager_from(m))
        args.setdefault("subject", "Job update")
        args.setdefault("body", "Work completed; documentation ready for review.")
    elif tool == "query_jobs":
        args.setdefault("property", _extract_property_unit(m)[0])
    # finalize_invoice takes no required args.
    return args, notes


def llm_route(message: str) -> ToolCall:
    """Route via Anthropic function calling. Raises on any failure so the caller
    can fall back to the keyword router."""
    client = llm.get_client()
    response = client.messages.create(
        model=llm.model_name(),
        max_tokens=512,
        system=_LLM_SYSTEM,
        tools=_LLM_TOOLS,
        tool_choice={"type": "any"},  # force the model to select a registered tool
        messages=[{"role": "user", "content": message}],
    )

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("LLM router returned no tool call")

    args, notes = _complete_args(tool_use.name, message, dict(tool_use.input or {}))
    return ToolCall(
        tool_use.name,
        args,
        f"LLM router ({llm.model_name()}) selected {tool_use.name}.",
        notes,
    )

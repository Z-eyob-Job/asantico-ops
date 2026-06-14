"""The agent loop: message in -> route -> policy check -> (approve) -> execute.

State is kept per conversation so a gated action can pause for approval and
resume on the user's next message. This mirrors the LangGraph HITL approval gate
from asantico-copilot; in production the graph nodes are router, policy, execute,
and respond, with an interrupt at the policy node for gated actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src import policy
from src.agent.router import ToolCall, route
from src.observability import log_event, new_trace_id
from src.tools import registry


@dataclass
class Conversation:
    pending: ToolCall | None = None
    history: list = field(default_factory=list)


class Agent:
    def __init__(self):
        self._convos: dict[str, Conversation] = {}

    def _convo(self, conv_id: str) -> Conversation:
        return self._convos.setdefault(conv_id, Conversation())

    def handle(self, conv_id: str, message: str) -> str:
        convo = self._convo(conv_id)
        text = message.lower().strip()
        trace_id = new_trace_id()
        log_event("message_received", conv_id, trace_id, message=message)

        # Resolve a pending gated action first.
        if convo.pending is not None:
            if text in ("approve", "yes", "confirm", "ok"):
                call = convo.pending
                convo.pending = None
                log_event("approval_granted", conv_id, trace_id, tool=call.tool, args=call.args)
                result = registry.call(call.tool, **call.args)
                log_event("tool_executed", conv_id, trace_id, tool=call.tool, gated=True)
                return self._format(call.tool, result, approved=True)
            if text in ("cancel", "no", "stop"):
                tool = convo.pending.tool
                convo.pending = None
                log_event("approval_denied", conv_id, trace_id, tool=tool)
                return "Cancelled. Nothing was sent or finalized."
            # Anything else: re-prompt.
            log_event("approval_pending_reprompt", conv_id, trace_id)
            return "There is an action waiting. Reply 'approve' or 'cancel'."

        # Fresh message: route to a tool.
        call = route(message)
        convo.history.append(message)
        log_event("routed", conv_id, trace_id, tool=call.tool,
                  rationale=call.rationale, risk=policy.risk_of(call.tool).value)

        if policy.needs_approval(call.tool):
            convo.pending = call
            log_event("approval_requested", conv_id, trace_id, tool=call.tool, args=call.args)
            return policy.approval_prompt(call.tool, call.args)

        result = registry.call(call.tool, **call.args)
        log_event("tool_executed", conv_id, trace_id, tool=call.tool, gated=False)
        return self._format(call.tool, result, approved=False)

    @staticmethod
    def _format(tool: str, result: dict, approved: bool) -> str:
        if tool == "knowledge_base":
            srcs = ", ".join(sorted({h["source"] for h in result["sources"]}))
            return f"{result['answer']}\n(sources: {srcs})"
        if tool in ("generate_invoice", "generate_estimate"):
            return (f"{result['document'].title()} drafted for {result['property']} "
                    f"unit {result['unit']}: subtotal ${result['subtotal']}, "
                    f"tax ${result['tax']} (10.55%), total ${result['total']}. "
                    f"Status: {result['status']}. Reply to finalize or send.")
        if tool == "triage_work_order":
            return (f"Triaged: {result['urgency']} / {result['trade']}. {result['note']}")
        if tool == "compute_tax":
            return (f"Subtotal ${result['subtotal']}, tax ${result['tax']} "
                    f"(10.55%), total ${result['total']}.")
        if tool == "draft_client_message":
            return f"Draft to {result['to']}:\n{result['body']}\n(Not sent. Approve to send.)"
        if tool in ("send_client_message", "finalize_invoice"):
            verb = "sent" if tool == "send_client_message" else "finalized"
            return f"Done. Action {verb}: {result}"
        if tool == "query_jobs":
            return f"Jobs for {result['property']}: {result['jobs']}"
        return str(result)

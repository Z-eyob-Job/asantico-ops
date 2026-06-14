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

        # Resolve a pending gated action first.
        if convo.pending is not None:
            if text in ("approve", "yes", "confirm", "ok"):
                call = convo.pending
                convo.pending = None
                result = registry.call(call.tool, **call.args)
                return self._format(call.tool, result, approved=True)
            if text in ("cancel", "no", "stop"):
                convo.pending = None
                return "Cancelled. Nothing was sent or finalized."
            # Anything else: re-prompt.
            return "There is an action waiting. Reply 'approve' or 'cancel'."

        # Fresh message: route to a tool.
        call = route(message)
        convo.history.append(message)

        if policy.needs_approval(call.tool):
            convo.pending = call
            return policy.approval_prompt(call.tool, call.args)

        result = registry.call(call.tool, **call.args)
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

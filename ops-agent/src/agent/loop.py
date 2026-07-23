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

# Control words steer a pending approval; they are never a request on their own.
APPROVE_WORDS = ("approve", "yes", "confirm", "ok")
CANCEL_WORDS = ("cancel", "no", "stop")
CONTROL_WORDS = APPROVE_WORDS + CANCEL_WORDS


@dataclass
class Conversation:
    pending: ToolCall | None = None
    history: list = field(default_factory=list)
    last_draft: dict | None = None  # most recent drafted client message, by conv
    last_invoice: dict | None = None  # most recent drafted invoice, for finalize
    active_job: dict | None = None  # parsed work order driving this conversation


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
            if text in APPROVE_WORDS:
                call = convo.pending
                convo.pending = None
                log_event("approval_granted", conv_id, trace_id, tool=call.tool, args=call.args)
                result = registry.call(call.tool, **call.args)
                log_event("tool_executed", conv_id, trace_id, tool=call.tool, gated=True)
                return self._format(call.tool, result, approved=True)
            if text in CANCEL_WORDS:
                tool = convo.pending.tool
                convo.pending = None
                log_event("approval_denied", conv_id, trace_id, tool=tool)
                return "Cancelled. Nothing was sent or finalized."
            # Anything else: re-prompt.
            log_event("approval_pending_reprompt", conv_id, trace_id)
            return "There is an action waiting. Reply 'approve' or 'cancel'."

        # A bare control word with nothing pending controls nothing. Never route
        # it to a tool. This is enforced before routing, so it holds identically
        # for the keyword and the LLM router backends.
        if text in CONTROL_WORDS:
            log_event("control_word_no_pending", conv_id, trace_id, word=text)
            return ("There is nothing waiting to approve or cancel. "
                    "Send a request first, then I can act on it.")

        # Fresh message: route to a tool.
        call = route(message)
        convo.history.append(message)
        log_event("routed", conv_id, trace_id, tool=call.tool,
                  rationale=call.rationale, risk=policy.risk_of(call.tool).value)
        for note in call.notes:
            log_event("assumption", conv_id, trace_id, tool=call.tool, note=note)

        if policy.needs_approval(call.tool):
            # Safety: the operator must approve the exact text that will be sent.
            # If a client message was drafted earlier in this conversation, carry
            # that reviewed draft into the gated send instead of a generic body.
            if call.tool == "send_client_message" and convo.last_draft is not None:
                call.args["to"] = convo.last_draft.get("to", call.args.get("to"))
                call.args["subject"] = convo.last_draft.get("subject", call.args.get("subject"))
                call.args["body"] = convo.last_draft.get("body", call.args.get("body"))
                log_event("send_uses_reviewed_draft", conv_id, trace_id, tool=call.tool)
            # Finalize the exact invoice the operator drafted, so the approved
            # PDF matches what they reviewed.
            if call.tool == "finalize_invoice" and convo.last_invoice is not None:
                call.args["property"] = convo.last_invoice.get("property", "")
                call.args["unit"] = convo.last_invoice.get("unit", "")
                call.args["line_items"] = convo.last_invoice.get("line_items", [])
                for key in ("scope_items", "work_order", "job_site"):
                    if convo.last_invoice.get(key):
                        call.args[key] = convo.last_invoice[key]
                log_event("finalize_uses_drafted_invoice", conv_id, trace_id, tool=call.tool)
            convo.pending = call
            log_event("approval_requested", conv_id, trace_id, tool=call.tool, args=call.args)
            return policy.approval_prompt(call.tool, call.args)

        # Draft edits: merge "add X for $Y" / "make the total $Z" into the
        # document the operator is looking at, then re-render it. A target
        # total is interpreted as the pre-tax subtotal, balanced with a Labor
        # line - and that interpretation is surfaced as a note, never silent.
        if call.tool in ("generate_estimate", "generate_invoice") and "edit" in call.args:
            edit = call.args.pop("edit")
            base = convo.last_invoice
            if base is None:
                return ("There is no draft to edit yet. Load a work order or ask "
                        "for an estimate first.")
            items = list(base.get("line_items", []))
            if edit.get("add"):
                added = edit["add"]
                items.extend(added if isinstance(added, list) else [added])
            if edit.get("target_subtotal") is not None:
                current = sum(li.get("amount", 0) for li in items)
                diff = round(edit["target_subtotal"] - current, 2)
                if abs(diff) >= 0.01:
                    label = "Labor" if diff > 0 else "Adjustment (discount)"
                    items.append({"description": label, "amount": diff})
                    call.notes.append(
                        f"interpreted {edit['target_subtotal']:.2f} as the pre-tax "
                        f"subtotal and added a {label} line of {diff:.2f} to reach it; "
                        "tax is computed on top.")
            call.tool = ("generate_invoice" if base.get("document") == "invoice"
                         else "generate_estimate")
            call.args["property"] = base.get("property", "Unknown Property")
            call.args["unit"] = base.get("unit", "NA")
            call.args["line_items"] = items
            for key in ("scope_items", "work_order", "job_site"):
                if base.get(key):
                    call.args[key] = base[key]
            log_event("draft_edited", conv_id, trace_id, tool=call.tool, edit=edit)

        # An active work order fills in what the message left out, so "make the
        # estimate" after "workorder <file>" documents the parsed job - any
        # property, not just the ones the extractor knows.
        if call.tool in ("generate_estimate", "generate_invoice") and convo.active_job:
            job = convo.active_job
            explicit_price = not any("assumed" in n for n in call.notes)
            if call.args.get("property") in ("Unknown Property", "", None):
                call.args["property"] = job.get("property", "Unknown Property")
            if call.args.get("unit") in ("NA", "", None):
                call.args["unit"] = job.get("unit", "NA")
            if job.get("priced_items") and not explicit_price:
                call.args["line_items"] = job["priced_items"]
                call.notes = [n for n in call.notes if "assumed" not in n]
            call.args["scope_items"] = [t["description"] for t in job.get("tasks", [])]
            if job.get("work_order"):
                call.args["work_order"] = job["work_order"]
            site = [f"<b>{job.get('property','')} #{job.get('unit','')}</b>"]
            if job.get("address"):
                site.append(job["address"])
            call.args["job_site"] = site
            log_event("document_uses_work_order", conv_id, trace_id,
                      tool=call.tool, work_order=job.get("work_order", ""))
        if call.tool == "draft_client_message" and convo.active_job:
            job = convo.active_job
            call.args["subject"] = (f"{job.get('property','')} #{job.get('unit','')} "
                                    "work order update").strip()
            if call.args.get("manager") == "the manager" and job.get("email_from_name"):
                call.args["manager"] = job["email_from_name"]
            tasks = [t["description"] for t in job.get("tasks", [])][:8]
            call.args["context"] = (f"{job.get('property','')} unit {job.get('unit','')}; "
                                    f"completed tasks: {', '.join(tasks)}")

        result = registry.call(call.tool, **call.args)
        log_event("tool_executed", conv_id, trace_id, tool=call.tool, gated=False)
        if call.tool in ("load_work_order", "fetch_email_work_order") and result.get("ok"):
            convo.active_job = result  # this job now drives documents and drafts
        if call.tool == "draft_client_message":
            convo.last_draft = result  # remember the reviewed draft for a later send
        if call.tool in ("generate_invoice", "generate_estimate"):
            # Remember the drafted document so a later gated finalize renders the
            # exact line items the operator reviewed (estimate -> invoice flow).
            convo.last_invoice = result
        reply = self._format(call.tool, result, approved=False)
        if call.notes:
            reply += "\nNote: " + " ".join(call.notes)
        return reply

    @staticmethod
    def _format(tool: str, result: dict, approved: bool) -> str:
        if tool in ("load_work_order", "fetch_email_work_order"):
            if not result.get("ok"):
                return result.get("error", "Could not read that work order.")
            c = result.get("contact", {})
            priced = ", ".join(f"{i['description']} (${i['amount']:.2f})"
                               for i in result.get("priced_items", [])) or "none"
            return (f"Work order loaded: {result['property']} #{result['unit']}"
                    f"{' — ' + result['address'] if result.get('address') else ''}"
                    f"{' — WO ' + result['work_order'] if result.get('work_order') else ''}.\n"
                    f"{result['task_count']} tasks found, {result['priced_count']} priced: {priced}.\n"
                    f"Assignee: {c.get('name') or 'unknown'} {c.get('email','')} {c.get('phone','')}\n"
                    "This job now drives estimates, invoices, and drafts. Say "
                    "'make the estimate' or 'make the invoice'."
                    + (f"\n(from email: {result.get('email_from')} - "
                       f"{result.get('email_subject')})" if result.get("email_from") else ""))
        if tool == "knowledge_base":
            srcs = ", ".join(sorted({h["source"] for h in result["sources"]}))
            return f"{result['answer']}\n(sources: {srcs})"
        if tool in ("generate_invoice", "generate_estimate"):
            reply = (f"{result['document'].title()} drafted for {result['property']} "
                     f"unit {result['unit']}: subtotal ${result['subtotal']}, "
                     f"tax ${result['tax']} (10.55%), total ${result['total']}. "
                     f"Status: {result['status']}. Reply to finalize or send.")
            if result.get("pdf"):
                reply += f"\nPDF written: {result['pdf']}"
            return reply
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

# Asantico Operations Agent: Technical Report (Draft, Sections 1-3)

Author: Eyob Worku
Course: AI410 Final Project
Draft date: June 26, 2026
Repository: https://github.com/Z-eyob-Job/asantico-ops

Note on scope: this draft covers sections 1 through 3 as required at the Week 9
checkpoint. Sections 4 and beyond (full results, limitations, future work,
conclusion) follow at final submission. Every metric and code reference below is
reproducible from the repository at the commit submitted for this checkpoint.

## 1. Problem Statement and Business Context

### 1.1 The operator and the work

Asantico is a real property maintenance business serving more than fifty
residential units around Seattle under a contract with Avenue One Residential.
The operator runs the business from a phone, between job sites. The day to day is
a stream of small, repetitive, error sensitive tasks: logging an incoming repair
request, deciding how urgent it is and which trade it needs, pricing an estimate
or invoice with the correct local tax, writing a short note to the property
manager, and answering recurring questions about company policy and billing
rules. None of this is hard in isolation. The cost is that it is constant, it
interrupts field work, and a single arithmetic or wording mistake on a financial
document or a client message has real consequences.

### 1.2 Why this is a good fit for an agent, and why most agents are unsafe for it

The work is well suited to an assistant that can be reached the way the operator
already communicates and that understands the business rules. The obstacle is
trust. An agent that can price an invoice can also send the wrong one. An agent
that can draft a client note can also send it to the wrong person, or quote a
dollar figure the contract says should never appear in a client email. For a
one person business, an autonomous assistant that acts on money or clients
without a checkpoint is a liability rather than a tool.

The business has hard, non negotiable rules that an agent must encode rather than
approximate. Sales tax is the Seattle combined rate of 10.55 percent, applied to
every line item including labor, not only to materials. The company name on every
document is "Asantico" and never "Asantico LLC." Tenant names never appear on any
document. Client emails are brief and never state a dollar amount in the body.
These are not preferences; they are the difference between a usable document and
one that has to be redone or that creates a tax or privacy problem.

### 1.3 What this project delivers

The Asantico Operations Agent is a local first operations assistant. It runs as a
long lived process on the operator's own machine. The operator reaches it from a
chat application, sends a plain language request, and the agent triages work
orders, prices estimates and invoices with the correct tax, drafts client
messages, and answers policy questions from the business's own knowledge base.
The defining property is the safety gate: every action that spends money,
finalizes a financial document, or contacts a real client pauses for explicit
human approval before it runs. Reads and drafts are free; sends and
finalizations are gated. This is what makes it safe for a small business to hand
real operations to an agent.

### 1.4 Success criteria

The project is successful if it meets the acceptance criteria frozen in the
specification: gated actions cannot execute without approval and this is proven
by tests; unregistered tools are denied; tax math matches the existing Asantico
engine to the cent; the knowledge base answers a fixed question set at hit rate
0.90 or above and MRR 0.80 or above; and the system runs end to end offline with
no API keys so that it is reproducible for development and grading.

## 2. Architecture and Framework Rationale

### 2.1 System shape

The system has two parts that compose into one product. The ops-agent is the
product surface: a gateway process that owns one or more channels, runs an agent
loop, and routes replies back to whoever messaged. The knowledge-rag subsystem is
the grounded retrieval engine behind the agent's knowledge_base tool, built as a
LlamaIndex pipeline over the Asantico knowledge corpus.

The agent itself is a pipeline of four responsibilities: route a message to a
tool, check that tool against the approval policy, execute it (after approval if
gated), and format a reply. State is held per conversation so that a gated action
can pause for approval and resume on the user's next message. The gateway,
channels, tools, and policy shape follows the local first, long lived process
pattern rather than a hosted request and response service, because the operator's
client and tenant data must stay on their own machine.

### 2.2 The safety gate as the central design decision

The approval policy is the architectural spine, not a feature bolted on at the
end. Every tool the agent can call is registered in a single policy table with a
risk class: READ for tools with no side effects, DRAFT for tools that produce a
document or message but do not send or finalize it, and GATED for tools that
spend money, finalize a document, or contact a client. A tool that is not
registered is denied by default. This least authority default means a routing
mistake cannot silently execute an unknown action.

The gate is enforced in more than one place, which is deliberate defense in
depth. The agent loop checks the policy before executing any routed tool and
parks gated actions in a pending state until the operator replies "approve" or
"cancel." The same policy is enforced independently at the MCP server boundary,
so a client reaching the tools over the Model Context Protocol cannot bypass the
gate either. The committed logs show this second path firing: an MCP call to
send_client_message without approval produces an mcp_gated_blocked event and does
nothing, while the same call with approval proceeds to a result.

### 2.3 Framework choice and rationale

The architecture composes two frameworks that were already proven in earlier
Asantico work rather than inventing a new runtime. The knowledge_base tool is the
existing knowledge-rag LlamaIndex retrieval pipeline. The agent loop with its
human in the loop interrupt at the policy node is the LangGraph approval pattern
from the asantico-copilot project. The reason for composing rather than building
from scratch is that this is an ambitious agent shipped by a single developer:
the realistic way to ship it well is to reuse parts that already work and have
tests, and to spend the limited build budget on the integration and the safety
properties that are specific to this business.

A second deliberate choice is the swappable router. In production the router is
an LLM doing function calling over the tool registry. For development, grading,
and reproducibility the project ships a deterministic keyword router with an
identical interface: message in, tool call out. Because the interface is
identical, swapping the LLM router in does not touch the agent loop or the policy
layer. This is what lets the entire system, including the demo and the test
suite, run offline with no keys, while leaving a clean seam for the production
router. The same swappable backend principle applies to the embeddings in the
retrieval pipeline, which default to an offline hash backend and can be changed
by configuration to a hosted or local model.

### 2.4 Observability

Every side effecting step in the agent emits one structured, trace correlated log
event. The project treats this as an invariant: if a step is not logged, it did
not happen. The events name the conversation, a trace id that ties one user
interaction together, the tool, its risk class, and the outcome. This is what
turns the safety claim from an assertion into something a reviewer can audit
after the fact, and it is the evidence base for the HITL validation in this
checkpoint.

## 3. Implementation Progress and Validation Evidence

### 3.1 What is built and working

At this checkpoint the safe spine of the system is complete and runs end to end
offline. The following are implemented and exercised by the demo and the test
suites:

- The gateway and the agent loop, including per conversation approval state that
  pauses a gated action and resumes it on approval or cancellation.
- The approval policy with its three risk classes, the deny by default behavior
  for unregistered tools, and enforcement in both the agent loop and the MCP
  server boundary.
- A working CLI channel that runs with no keys, plus channel adapters for
  Telegram, email, and WhatsApp that share one base interface (Telegram and email
  are the next channels to be wired; WhatsApp is deferred and out of scope).
- The tool layer covering knowledge base lookup, work order triage, tax
  computation, estimate and invoice drafting, and client message drafting and
  sending, with the Asantico business invariants enforced in the tool layer.
- The MCP server exposing the tools over the Model Context Protocol with the gate
  enforced.
- Structured, trace correlated observability writing JSON events for every step.
- A reproducible environment pinned with uv, and a GitHub Actions CI workflow
  that runs Ruff lint and both test suites on every push.

### 3.2 Validation evidence

Tests. Both suites pass at this checkpoint: 13 tests in the ops-agent suite
covering the approval gate, routing, tax math, policy denial of unregistered
tools, and the MCP and observability paths, and 6 tests in the knowledge-rag
suite covering the evaluation math. Lint passes with no findings.

Tax correctness. The tax invariant is verified both by unit tests and in the live
session: an estimate for a 420.00 dollar subtotal produces 44.31 dollars of tax
at 10.55 percent and a 464.31 dollar total, matching the Asantico engine to the
cent.

Retrieval quality. The knowledge-rag pipeline is evaluated on a fixed ten
question set with the offline backend and meets the acceptance bar: hit rate
0.900 and MRR 0.850, against targets of 0.90 and 0.80. The per query breakdown is
in the evaluation report under docs/week9/evidence. One query (Q7) misses on the
offline hash embedding backend, which is the known failure mode driving the move
to a stronger embedding backend in production.

Human in the loop behavior. A full end to end CLI session, captured in
docs/week9/evidence/cli-session-transcript.txt, demonstrates the gate. A question
routes to the grounded knowledge base and returns an answer with its source. A
reported leak is triaged as an emergency in the plumbing trade and escalated. An
estimate is priced with correct tax. A drafted client message is produced freely.
A request to send a client message stops the agent, which emits an
approval_requested event and does nothing until the operator replies "approve,"
at which point approval_granted and then tool_executed are logged and only then
is the action carried out. The committed log file at docs/week9/evidence shows
the same behavior on both the loop path and the MCP path.

### 3.3 What remains, and the path to readiness

The spine is complete; the work remaining is to replace the offline stubs with
the real Asantico engines and to ship a real chat channel. Specifically: wrap the
real asantico-cli tax and ReportLab document engines and the real triage logic
into the tool layer; wire the knowledge-rag LlamaIndex pipeline behind the
knowledge_base tool so retrieval uses the production engine rather than the demo
path; implement the Telegram channel end to end with approval state keyed by chat
id; add tests for each wrapper and the channel; and swap the keyword router for an
LLM function calling router behind the same interface. The current backlog status
and the Week 9 sprint scope are detailed in the backlog completion report under
docs/week9. None of this remaining work changes the architecture or the safety
model, which are frozen and already enforced by tests; it connects the proven
parts to production engines and a real channel.

### 3.4 Reproduce the evidence

```
git clone https://github.com/Z-eyob-Job/asantico-ops.git
cd asantico-ops

# Knowledge base retrieval metrics
cd knowledge-rag && pip install -r requirements.txt
python -m src.ingest && python -m src.evaluate     # hit rate 0.900, MRR 0.850

# Tests and lint
cd ../ops-agent && python -m pytest tests/ -q       # 13 passed
cd ../knowledge-rag && python -m pytest tests/ -q   # 6 passed
ruff check ..

# Live HITL session (paste the messages in DEMO.md)
cd ../ops-agent && python -m src.gateway
```

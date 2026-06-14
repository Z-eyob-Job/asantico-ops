# SPEC: Asantico Operations Agent

Status: scope frozen; implementation in progress
Last updated: June 14, 2026

## 0. Constitution (non-negotiable principles)

These principles bind every change and override convenience or feature pressure.

C1. Safety gate is absolute. Any action that spends money, finalizes a financial
document, or contacts a real client requires explicit human approval. No code path,
channel, or protocol surface may bypass it.
C2. Least authority. Tools default to deny. A tool that is not registered in the
policy with a risk class cannot run.
C3. Everything is observable. Every side-effecting step emits a structured,
correlated log event. If it is not logged, it did not happen.
C4. Local-first and private. Client and tenant data stay on the operator's machine.
Tenant names never appear on documents; client messages never state amounts.
C5. Reproducible. The system runs offline with no keys for development and grading,
and dependencies are pinned and lockable with uv.
C6. Compose, do not reinvent. Reuse the existing asantico-cli engines and the
asantico-copilot approval pattern rather than rebuilding them.

## 1. Problem and motivation

A small property-maintenance operator runs the business from their phone, between
jobs. The repetitive work (logging a request, triaging urgency, pricing an
estimate with the right tax, writing a brief client note, answering "what is our
minimum charge again") is exactly the work an agent can absorb, if it can be
reached the way the operator already communicates and if it never acts on money
or clients without a human in the loop. The Asantico Operations Agent is that
assistant: local-first, reachable from a chat app, grounded in the business's own
rules, and gated on every risky action.

## 2. Scope

In scope: a long-lived local gateway; a channel-agnostic adapter layer with a
working CLI channel and Telegram plus email as the first real channels; an agent
loop with per-conversation approval state; a tool layer covering knowledge base,
work-order triage, tax, estimate and invoice drafting, and client-message
drafting; and an approval policy that gates sends and finalizations.

Out of scope: a hosted multi-tenant SaaS, payments processing, accounting-system
sync, fully autonomous sending without human approval, and the WhatsApp channel
(deferred: the Business Cloud API onboarding is out of scope for this project).
The supported channels are the CLI demo plus Telegram and email.

## 3. Functional requirements

FR1. Run as one local process reachable from at least one chat channel.
FR2. Accept a natural-language message and select the correct tool.
FR3. Triage a work order into urgency and trade, escalating emergencies.
FR4. Compute Seattle tax at 10.55% on every line item including labor.
FR5. Draft estimates and invoices with no tenant name and the name "Asantico".
FR6. Answer policy and tax questions from a grounded knowledge base with sources.
FR7. Draft brief client messages that never state a dollar amount.
FR8. Require explicit human approval before sending a message or finalizing an invoice.
FR9. Preserve approval state per conversation so a gated action can pause and resume.
FR10. Deny any tool not registered in the policy.

## 4. Non-functional requirements

NFR1. Local-first: client and tenant data stay on the operator's machine.
NFR2. Offline-reproducible: the CLI demo and tests run with no keys.
NFR3. Swappable backends: LLM router and embeddings change via configuration.
NFR4. Safety by construction: gated actions cannot run without approval, proven by tests.
NFR5. Channel-agnostic: adding a channel never changes the agent or policy.

## 5. Architecture decision

Framework: LlamaIndex for the knowledge_base tool plus a LangGraph agent loop with
a human-in-the-loop interrupt at the policy node. Rationale: the knowledge base is
the knowledge-rag LlamaIndex pipeline already built, and the approval gate is the
asantico-copilot LangGraph pattern already built; this project composes proven
parts rather than inventing a runtime, which is the realistic way to ship an
ambitious agent solo. The gateway-plus-channels-plus-tools-plus-policy shape is
taken from OpenClaw. See `docs/architecture-diagram.svg`.

## 6. Build phases

Phase 1, spine: gateway, agent loop, policy, CLI channel, knowledge_base tool (done in this skeleton).
Phase 2, real tools: wrap the real asantico-cli for tax, estimate, invoice, triage; wire the LlamaIndex RAG.
Phase 3, real channel: Telegram end to end, then email; per-chat approval state.
Phase 4, router and polish: swap the keyword router for an LLM function-calling router; demo and docs.

Executed across the five agent lanes in `DELEGATION.md`.

## 7. Evaluation and acceptance

Safety tests must pass: every gated action requires approval, no draft sends
without approval, unregistered tools are denied. Tax math matches the existing
engine to the cent. The knowledge_base tool answers a fixed question set with
hit rate at or above 0.90 and MRR at or above 0.80 once on the real RAG backend.
One end-to-end demo over Telegram: message in, work done, approval honored.

## 8. Risks and mitigations

LLM router misfires and calls the wrong tool; mitigation is the policy gate (a
misfire on a gated action still stops for approval) plus router tests. The agent
leaks tenant data; mitigation is local-first plus the no-tenant-name rule enforced
in the tool layer. WhatsApp onboarding stalls; mitigation is shipping Telegram and
email first so the project is complete without it. Knowledge base is stale;
mitigation is re-indexing on a schedule and citing sources so answers are checkable.

## 9. Resolved decisions

Solo project. Channels are the CLI demo plus Telegram then email; WhatsApp is
deferred and out of scope for now. All four tool areas in scope
(invoice/estimate/tax, triage, knowledge base, client messages). Local-first with
mandatory approval gates on money and client contact.

## 10. Implementation plan

The plan moves from a safe spine outward, hardening before scaling.

Stage A (done): the spine - gateway, agent loop with per-conversation HITL state,
approval policy, CLI channel, knowledge_base tool, structured observability, an MCP
server exposing the tools, CI, and uv environment.

Stage B: real tools - replace the domain stubs with calls into the real asantico-cli
(tax engine, ReportLab PDFs, triage agent) and wire the knowledge-rag LlamaIndex
pipeline behind the knowledge_base tool.

Stage C: real channel - Telegram end to end (then email), with approval state keyed
by chat id, running as a persistent local process.

Stage D: intelligence and polish - swap the keyword router for an LLM
function-calling router (policy gate still enforced), then production hardening
(secrets, retries, rate limits).

## 11. Task breakdown

P0 (foundation, done): spine, policy gate, observability, MCP server, CI, uv, SPEC,
architecture diagram, risk register, demo evidence.

P1 (next): real asantico-cli tool wrappers (Cursor); knowledge-rag wired behind
knowledge_base (Claude); Telegram channel (Cursor, key from Eyob); tests for every
wrapper and the channel (Codex); LLM router (Cursor, review by Claude).

P2 (stretch): email channel; skills as SKILL.md packs; scheduled reminders; WhatsApp
(deferred). See `BACKLOG.md` for the full owned list.

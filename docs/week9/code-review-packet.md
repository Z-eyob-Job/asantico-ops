# Code Review Packet (Week 9)

Project: Asantico Operations Agent
Date: June 26, 2026

This packet has three parts. Part A is an internal review of the codebase against
the project's own constitution and quality bar, with specific findings. Part B is
the slot for the external peer team's feedback received in the Week 9 cross team
review. Part C records the response actions taken or planned for each piece of
feedback. Parts B and C must be filled with the real feedback from the actual
review session; do not submit them with placeholder content.

## Part A. Internal review against the constitution

Scope reviewed: ops-agent/src (policy, agent loop, router, tools, channels, MCP
server, observability) and knowledge-rag/src (ingest, retrieve, embeddings,
evaluate). Reviewed for architecture coherence and requirement traceability,
error handling and logging, test coverage and reproducibility, and the safety and
responsible AI safeguards that are this project's reason to exist.

### Strengths confirmed

- Safety gate is real and enforced in two independent places. The agent loop
  parks gated actions in a pending state and will not execute without an explicit
  approve, and the MCP server enforces the same policy at its own boundary
  (mcp_gated_blocked is visible in the committed logs). This is genuine defense in
  depth, not a single check.
- Deny by default is implemented correctly. risk_of raises on any tool not in the
  policy table, so an unregistered tool cannot run. This traces directly to
  constitution principle C2 and is covered by a test.
- Observability is consistent. Every side effecting step emits a structured event
  with a trace id tying one interaction together. This makes the safety claims
  auditable rather than asserted.
- Reproducibility holds. Both suites pass offline with no keys (13 ops-agent, 6
  knowledge-rag), lint is clean, and the retrieval eval reproduces at hit rate
  0.900 and MRR 0.850.

### Findings to address

1. Drafted message is not carried into the gated send. In router.py the
   send_client_message branch builds a fixed body ("Work completed; documentation
   ready for review.") rather than reusing the message produced by a prior
   draft_client_message call. The result is that the approved send may not match
   the draft the operator reviewed. This is a correctness and trust gap: the
   operator should approve the exact text that gets sent. Recommend threading the
   most recent draft for a conversation into the send, or having the send require
   a reference to a specific draft. Priority: high, because it touches the gated
   path.

2. Keyword router is brittle and order dependent. route() resolves intent by
   substring checks in a fixed order, so phrasing like "invoice" inside a question
   or overlapping keywords can misroute. The mitigation is acknowledged (the LLM
   router is the P1 replacement and the gate catches gated misroutes), but until
   then the router deserves a few more adversarial tests, especially around
   messages that mix a question with an action verb.

3. Amount extraction can still collide with identifiers. _extract_amount prefers a
   dollar sign and falls back to a "for or of or at" number, which mitigates the
   unit number problem, but a message like "estimate for unit 208" with no price
   will default the line item to 150.0 silently. Recommend logging when a default
   amount is substituted so the operator can see that a number was assumed rather
   than parsed.

4. Channel stubs lack tests and a clear not implemented contract. telegram.py and
   email_channel.py exist against the base interface but are not yet wired or
   tested. Recommend each stub raise a clear NotImplementedError with a message
   pointing at the backlog item, and add a test asserting the gateway selects the
   right channel class, so the seam is verified before the real implementation
   lands.

5. RAG Q7 miss is unexplained in the report. The evaluation report records that
   Q7 misses but not why. Recommend a one line failure note per missing query in
   the eval output (for example, the relevant chunk's vocabulary does not overlap
   the query under the hash backend) so the reader can judge whether the real
   backend will fix it.

6. Minor: the Risk enum carries a noqa for UP042. Once on Python 3.11 plus, this
   can likely be resolved properly rather than suppressed; low priority.

### Traceability check

Functional requirements FR1 through FR10 in SPEC.md each map to code that exists:
the gateway and CLI channel (FR1), the router (FR2), triage (FR3), compute_tax at
10.55 percent (FR4), estimate and invoice drafting with no tenant name and the
"Asantico" name (FR5), the knowledge_base tool with sources (FR6), brief client
drafts with no dollar amount (FR7), the approval gate (FR8), per conversation
approval state (FR9), and deny by default (FR10). The gap is that FR4 through FR6
currently run against stubs rather than the real engines; closing that gap is the
P1 sprint, not an architecture change.

## Part B. External peer review feedback received

Reviewing team: __________________________
Date of review session: __________________________
Format (live, async, written): __________________________

Record each piece of feedback received as its own item. Capture the reviewer's
point in their words or a faithful summary, the area it touches, and how serious
they considered it.

| ID | Feedback received | Area | Severity (reviewer) |
|----|-------------------|------|---------------------|
| F1 | | | |
| F2 | | | |
| F3 | | | |
| F4 | | | |

## Part C. Response actions

For each feedback item above, record the action taken or the decision made,
including a deliberate decision not to act and why. Link a commit or backlog item
where the change landed.

| Ref | Action taken or planned | Status | Commit / backlog link |
|-----|-------------------------|--------|------------------------|
| F1 | | | |
| F2 | | | |
| F3 | | | |
| F4 | | | |

Summary of integration: in two or three sentences, state what the peer review
changed about the project and what you chose to leave as is, so a grader can see
that the feedback was genuinely weighed rather than just logged.

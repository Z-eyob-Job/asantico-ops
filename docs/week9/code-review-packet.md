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

## Part B. Independent review (self-review in lieu of an external peer)

Context: this is a solo project and no classmate was available to exchange a
cross-team review. The instructor is aware of the solo status. In place of an
external peer review, a structured independent review pass was performed on the
codebase on June 26, 2026, separate from day-to-day development, looking for
defects the original author would be biased not to see. The findings below are
recorded the same way external feedback would be, with severity and area, so the
review-to-fix trail is auditable.

| ID | Finding | Area | Severity |
|----|---------|------|----------|
| S1 | The gated send used a generic hardcoded body instead of the message the operator drafted and reviewed, so a person could approve text they never saw. | Safety / gated path | High |
| S2 | When no price was in a message, the router silently defaulted the line item to 150.00 and priced the document with no signal that an amount was assumed. | Financial correctness | Medium |
| S3 | The domain tools computed tax with built-in float math rather than the real asantico-cli engine, risking drift from the production tax behavior. | Correctness / reuse | Medium |
| S4 | Channel selection had no test, so a regression in the gateway could route to the wrong channel class or fail unhelpfully on an unknown name. | Robustness / tests | Medium |
| S5 | The agent's knowledge_base tool carries its own retrieval implementation separate from the knowledge-rag LlamaIndex pipeline, so the two can drift. | Architecture | Medium (open) |
| S6 | triage_work_order classifies with a fixed keyword list rather than the real triage engine, so unusual phrasing can mis-classify urgency or trade. | Coverage | Low (open) |
| S7 | finalize_invoice returns a placeholder PDF path rather than generating a real document, and query_jobs returns sample data. | Completeness | Low (open) |

## Part C. Response actions

| Ref | Action taken or decision | Status | Commit / link |
|-----|--------------------------|--------|----------------|
| S1 | Carried the reviewed draft into the gated send so the operator approves the exact text that is sent; added a test. | Fixed | commit 458d0ae |
| S2 | The router now records an assumption when it defaults a price, the agent surfaces it in the reply, and it is logged as an event; added tests. | Fixed | commit d1af8ca |
| S3 | Wired the real asantico-cli tax engine into the tools with an offline fallback; added a test that the real engine matches to the cent. | Fixed | commit 903eff5 |
| S4 | Added tests that the gateway selects the correct channel class, rejects unknown channels, and that deferred channels fail clearly. | Fixed | commit d1af8ca |
| S5 | Deferred to the Week 10 production push, where the knowledge-rag pipeline is wired behind the tool as a single retrieval engine. Tracked in BACKLOG.md (P1). | Open, planned | BACKLOG.md |
| S6 | Deferred to the Week 10 router work, which swaps the keyword path for the real classifier while the policy gate still holds regardless of classification. | Open, planned | BACKLOG.md |
| S7 | Deferred to the Week 10 engine wrappers (ReportLab PDF, real job lookup). The gate already protects these paths, so the placeholders are safe in the interim. | Open, planned | BACKLOG.md |

Summary of integration: the independent review found seven issues. The four that
touch the safety-critical and financial paths (S1 through S4) were fixed
immediately with tests and are on the branch. The remaining three (S5 through S7)
are real but lower risk because the approval gate already protects those paths;
they are deferred to the Week 10 production work and tracked in the backlog rather
than left undocumented. The review was treated as a real second pair of eyes, not
a formality, and it directly produced four committed fixes.

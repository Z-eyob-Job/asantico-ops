# Asantico Operations Agent: Technical Report

Author: Eyob Worku
Course: AI410, Human-Centered AI Interaction
Project: Final submission, local-first agentic operations assistant

## System at a glance

The Asantico Operations Agent is a working agentic system that lets a property
maintenance operator run real back-office work by sending a plain-language message
from a chat app. It answers policy and billing questions from a real retrieval
pipeline, prices invoices and estimates with the business's real tax and document
engines, triages incoming work orders, and drafts client messages. Every action
that spends money, finalizes a document, or contacts a client is held behind an
explicit human approval gate. The agent runs locally, needs no hosting, and falls
back to a dependency-free offline mode when no model or network is available, which
keeps it testable and reproducible on any machine.

The system has been verified end to end against a live model and over a real
Telegram channel: a message sent from a phone is routed by the model, answered from
the knowledge base with sources, and, when it asks the agent to contact a client,
stopped for approval before anything is sent. That single demonstrated behavior, a
real person directing real operations through a chat message with a human approval
checkpoint in the path, is the thesis of the project.

## 1. Problem statement and business justification

Asantico is a Seattle property maintenance business contracted with Avenue One
Residential, managing roughly fifty residential units. The day-to-day operational
load is not complicated work, but it is constant and detail-sensitive: a property
manager texts that a unit has a leak, an invoice needs to be generated for a unit
turn with the correct Seattle sales tax, an estimate needs to go out, a status
update needs to be sent to a manager. Each of these tasks is individually small and
collectively heavy, and each carries a quiet risk. A wrong tax figure, a message
sent to the wrong manager, a finalized invoice with an error, or a tenant name
written onto a client-facing document are all mistakes that cost money or trust.

The operator is a single person doing this alongside the actual maintenance work.
The natural instinct is to reach for a general AI assistant, but a general
assistant is the wrong tool here for one specific reason: it will act. If you ask a
general chat agent to send a message to a client, it sends it. For a business where
the difference between a draft and a sent message is the difference between a
reviewable mistake and a delivered one, an agent that acts without a checkpoint is a
liability rather than an aid.

The business justification for this project is therefore not "automate the work."
It is "make the work faster while making the irreversible parts safer than they are
today." The agent removes the friction of switching between tools, looking up the
tax rate, formatting an invoice, and recalling which manager owns which property,
while introducing a discipline that manual work does not enforce: nothing
irreversible happens without a human looking at the exact content and approving it.
The value is the combination. Speed alone is available from any assistant. Speed
plus a guaranteed approval checkpoint on every money-or-client action is what makes
this usable for a real business with real liability.

Concretely, the agent encodes the business's hard rules so they cannot be forgotten
under time pressure: Seattle sales tax at 10.55 percent is applied to every line
item including labor; the company name is always written as "Asantico"; tenant names
never appear on client-facing documents; and client messages do not state dollar
amounts in the body. These are not preferences, they are invariants the business
depends on, and embedding them in the tool layer means they hold on every run rather
than depending on the operator remembering them at eleven at night.

## 2. Architecture decisions and framework rationale

The system is organized as a small set of layers, each with one responsibility, so
that the safety-critical part stays small and auditable.

A channel receives a message and hands it to the agent, then delivers the reply.
Two channels are implemented: a command-line channel for local use and testing, and
a Telegram channel for real use from a phone. Channels share a common interface, so
adding one does not touch the agent or the safety logic. The gateway selects the
channel by name and runs the receive-handle-reply loop.

The agent loop is the core. It keeps state per conversation, so a gated action can
pause for approval and resume on the user's next message. On each message it first
resolves any pending approval, then guards against bare control words that have
nothing to act on, then routes the message to a tool, then consults the policy gate,
and only then either executes or pauses for approval. Keeping this sequence in one
readable function is a deliberate choice: the property that matters most, that no
gated action runs without approval, should be verifiable by reading a single file
rather than reconstructed across a framework's abstractions.

The router turns a message into a tool call. It has two interchangeable backends
behind one interface. The default is a deterministic keyword router that needs no
model, no key, and no network. The optional backend is an LLM function-calling
router that presents the tool registry to the model and lets it select exactly one
tool. Both return the identical tool-call shape, so the loop and the safety gate are
unaware of which router ran. The backend is chosen by an environment variable, and
if the model backend is requested but no key is present or the call fails, the
system logs a warning and falls back to the keyword router. This dual-backend design
is the single most important architectural decision in the project, and it is
discussed again in section 5, because it is what lets the safety guarantee hold
independently of the model.

The policy gate classifies every tool by risk. There are three classes. READ tools
have no side effects and run freely, such as answering from the knowledge base.
DRAFT tools produce a document or message but do not send or finalize anything, such
as drafting a client message or generating an invoice for review. GATED tools spend
money, finalize a document, or send to a client, and they require explicit human
approval before they run. The two gated tools are sending a client message and
finalizing an invoice. This three-way classification, rather than a binary
safe-or-unsafe split, is what lets the agent be genuinely useful: it can do all the
reading and drafting work freely and fast, and reserves the human's attention only
for the handful of actions that are actually irreversible.

The tool registry holds the callable tools and is the only place the agent reaches
real business logic. Tools wrap the business's real engines: the tax computation and
the ReportLab PDF generation come from the company's own command-line tool, wired in
with a dependency-free offline fallback so the system still runs and tests on a bare
machine. The knowledge tool is backed by the retrieval pipeline described in section
4. An MCP server exposes the same tools over the Model Context Protocol, so the
toolset is reusable by other Model Context Protocol clients, not locked to this
agent.

Observability runs underneath all of it. Every meaningful step emits a structured
log line with a trace id and conversation id: message received, routed with its
rationale and risk, approval requested, approval granted or denied, tool executed
with whether it was gated. This is what makes the safety claims checkable after the
fact rather than asserted, and it is what a reviewer reads to confirm the gate fired.

The framework rationale is deliberately conservative. The loop mirrors a LangGraph
human-in-the-loop approval pattern, with router, policy, execute, and respond as the
conceptual nodes and an interrupt at the policy node for gated actions, but it is
implemented directly rather than through a heavy graph framework. For a single-
operator system whose central requirement is an auditable safety checkpoint, a small
explicit loop is easier to read, test, and trust than a framework whose control flow
lives in configuration. The same conservatism explains the Telegram channel using
the standard library over an async bot framework: it adds no dependency, keeps the
synchronous channel contract simple, and lets the whole test suite run with no token
and no network.

## 3. Model selection and benchmark evidence

Model use in this system is deliberately bounded. The model is used for two things:
to route a message to a tool when the LLM router backend is enabled, and to generate
a short grounded answer from retrieved sources. It is never used to decide whether an
action is allowed, never used to perform a calculation, and never in the path that
sends or finalizes anything without approval. This boundary is the reason model
selection is a tuning decision rather than a safety decision: a better or worse model
changes answer quality and routing accuracy, but it cannot change what is gated.

The model is configurable through an environment variable, with a default of
claude-sonnet-4-6. The default favors Sonnet because the work here is well-scoped
tool selection and short grounded summarization over a small corpus, which does not
require the largest model, and a smaller fast model keeps latency and cost low for an
operator who may send many short messages. The configuration allows overriding to a
more capable model when desired; the live end-to-end verification described in
section 5 was run with claude-opus-4-7 selected through that override, which confirms
the swap is a one-variable change with no code modification.

The retrieval pipeline is evaluated on a fixed ten-question set with two standard
metrics. Hit rate is the fraction of questions where a relevant document appears
anywhere in the top results, and mean reciprocal rank averages the reciprocal of the
rank of the first relevant result, so it rewards placing the correct document first.
On the committed evaluation, the pipeline achieves a hit rate of 0.900 and a mean
reciprocal rank of 0.800, against an acceptance bar of 0.80 on mean reciprocal rank.
The single soft miss is one question where the relevant file is retrieved but at rank
two rather than rank one, which costs reciprocal rank without costing hit rate. This
is honest evidence: the pipeline finds the right document for nine of ten questions,
and ranks it first for eight of them.

The benchmark that most directly informs the design is not a leaderboard comparison
but this retrieval evaluation, because retrieval quality is what bounds answer
quality in a grounded system. A more capable generation model cannot fix a retrieval
miss; it can only phrase well whatever was retrieved. The evaluation therefore tells
us where the real headroom is, which is in retrieval ranking rather than in model
choice, and that finding is reflected in the future-work section. Earlier coursework
included a multi-model comparison across candidate models on a fixed prompt set with
a decision matrix; the conclusion that scoped tool-selection and short grounded
answers do not require the largest model is consistent with the Sonnet default chosen
here.

## 4. RAG and reasoning pipeline design

The knowledge tool answers policy, billing, and account questions from the business's
own documents rather than from the model's general knowledge, which is what keeps its
answers correct for this specific company. The pipeline has the five standard stages.

Ingestion reads the corpus of business documents, which cover billing workflow, tax
rules, company policies, client accounts, and work-order intake. Chunking splits each
document into overlapping passages sized so that a single rule or policy statement
stays intact within a chunk. Embedding and indexing convert each chunk to a vector
and build a searchable index. Retrieval, at query time, embeds the question and
returns the top matching chunks with their source file and a relevance score.
Generation, when a model is available, asks the model for a short answer grounded
strictly in those retrieved chunks, and the answer is always returned together with
its sources so a reader can verify it.

The pipeline has two backends behind one interface, mirroring the router design. The
default offline backend uses a deterministic hash-based embedding and needs no
dependencies, no key, and no network, which is what allows the knowledge tool to work
in tests and in the offline demo. The real backend uses the LlamaIndex retrieval
pipeline and is selected by an environment variable; if it is requested but its
dependencies are unavailable, the tool logs a warning and falls back to the offline
backend. Grounded generation is similarly gated: with no key, the tool returns the
retrieved snippets directly, and a separate environment variable can force that
deterministic behavior even when a key is present, which is what keeps the relevant
tests stable.

The reasoning path for a full request threads these pieces together. A message
arrives on a channel and reaches the agent loop. The router selects a tool. If the
selected tool is the knowledge base, retrieval runs and a grounded answer comes back
with sources. If the selected tool is a drafting tool, a document or message is
produced for review and remembered on the conversation. If the selected tool is a
gated tool, the loop pauses and asks for approval, and crucially, when the operator
approves a send, the agent sends the exact draft the operator already reviewed rather
than regenerating new text, so that approval applies to the precise content that goes
out. This carry-the-reviewed-draft detail is a small design decision with a real
safety payoff: it closes the gap where an approved action could otherwise execute
with different content than what was shown.

A note on determinism is important to the design. Retrieval and the business
calculations are deterministic; the same question returns the same sources and the
same tax figure every time. Only the grounded answer prose varies, because a live
model phrases the same facts differently across calls. The test suite is built around
this distinction: it asserts on the deterministic signals, the retrieved sources and
their order and the computed figures, and never on exact model wording. This is why
the suite is reliable even with a live model in the loop, and it is a lesson that
generalizes well beyond this project.

## 5. Responsible AI analysis: risks and mitigations

The central risk in any acting agent is that it takes an irreversible action that is
wrong, and the central design response in this system is to make that structurally
difficult rather than to hope the model behaves.

The primary risk is an unauthorized or incorrect client-facing action: a message
sent to a client, or an invoice finalized, that the operator did not intend. The
mitigation is the policy gate. Sending a client message and finalizing an invoice are
classified GATED, and the agent loop will not execute a gated tool without an explicit
approval, pausing instead to show the operator the exact action and its arguments.
The key property is that this gate sits after routing and is independent of which
router produced the tool call. This was verified two ways. A deterministic test forces
the LLM router into its worst case, selecting the client-send tool from an innocuous
message, and asserts that the loop still pauses for approval, that nothing is sent,
and that cancelling leaves nothing sent. And the same behavior was confirmed live over
a real Telegram channel from a phone: the model routed a send request to the gated
tool, the agent requested approval, and the send completed only after the operator
replied approve. The guarantee holds even if the model misroutes, because the gate,
not the model, enforces it.

A second risk is approval confusion across conversations, where one person's approval
could resolve another person's pending action. The mitigation is that all approval
state is keyed by conversation id, and on the Telegram channel the conversation id is
the chat id, so each chat has its own isolated pending state. This was verified: an
approval arriving in one chat cannot resolve a pending action in another, and a test
asserts that isolation directly.

A third risk is stray control words. A bare approve or cancel with nothing pending
must not be interpreted as a fresh instruction and routed to a tool. The mitigation
is an explicit guard before routing that catches control words with no pending action
and replies that there is nothing to approve, enforced before either router runs.

A fourth risk is content correctness on the documents the business depends on. The
mitigations are that the tax computation and PDF generation use the business's real,
tested engines rather than model output, that the business invariants are enforced in
the tool layer, and that grounded answers are returned with their sources so they can
be checked against the actual documents.

An honest analysis must also name where the system is not yet airtight. The business
maintains a set of style invariants for client-facing text, including no em dashes and
no dollar amounts in message bodies. The deterministic drafting path respects these
because it uses fixed templates. The live model, when it composes a client message
freely, can violate them; in live testing it produced a message body containing an em
dash. Because every send is gated, this is caught at the approval step by a human
rather than delivered, so it is a quality defect rather than a safety breach, but it
is a real gap and the fix is a deterministic post-filter on generated client text,
noted in future work. Disclosing this is part of responsible analysis: the gate
contains the failure, and the remaining work to make the generated text itself
compliant is identified rather than hidden.

Privacy and secret handling round out the analysis. Tenant names are kept off
client-facing documents by business rule. API keys and tokens are read only from the
environment, never hardcoded, never logged, and never written into tracked files; the
secret file is excluded from version control, and error logging is written to avoid
emitting any token-bearing URL.

## 6. Lessons learned and future work

The most useful lesson from this project is that the safety property and the model
should be decoupled, and that doing so makes both better. By putting the approval gate
after routing and behind a single function, the system can use a live model for the
parts models are good at, understanding intent and phrasing answers, without ever
letting the model's correctness become load-bearing for safety. The repeated
experience during development reinforced this: every time the live model behaved
differently than the deterministic path expected, the gate still held, and the only
things that needed fixing were quality details, not the safety guarantee. A design
that fails safe under model surprise is worth more than one that depends on the model
not surprising you.

A second lesson concerns testing in the presence of a non-deterministic model. The
instinct to assert on a model's exact output is a trap; those tests are brittle and
will fail for cosmetic reasons. Asserting instead on the deterministic substrate, the
retrieved sources, the computed numbers, the risk classification, the gate's behavior,
produces a suite that is both stable and meaningful. Several real test failures during
development were caused by this mistake and fixed by moving the assertions to
deterministic signals, which is a pattern worth carrying into any future model-backed
system.

A third lesson is the value of an offline, dependency-free default for everything that
touches a model or a network. The dual-backend design for both the router and the
knowledge pipeline meant the system was always runnable and testable on a bare
machine, which kept continuous integration honest and made the project reproducible by
anyone without credentials. Reproducibility was not an afterthought bolted on at the
end; it fell out of designing every external dependency with a local fallback from the
start.

Future work falls into clear tiers. The immediate next step is the generated-text
post-filter that enforces the business style invariants, including stripping em dashes
and ensuring no dollar amounts appear in client message bodies, so the live model's
drafts are compliant before they even reach the approval step. The retrieval evaluation
points to the next technical investment: the single soft miss at rank two reflects the
coarseness of the offline hash embedding, and moving the real backend to a stronger
embedding model is the documented lever to lift mean reciprocal rank toward and past
the current bar more comfortably. Beyond that, wrapping the business's real triage
classifier behind the triage tool, with the same offline fallback pattern, would
complete the toolset; this was scoped and deferred under time constraints in favor of
the safety-critical and documentation deliverables.

The larger horizon, honestly out of scope for a single-operator capstone but worth
naming, is the path to a hosted multi-user product: a persistent store for
conversations and approvals, authentication and per-operator isolation, a hosted
deployment so the agent runs without a laptop staying on, additional channels such as
WhatsApp, and integration with accounting and payment systems. None of these change
the core design; they build outward from it. The thing that would carry forward
unchanged is the part this project set out to prove: that a real person can run real
operations through a chat message, with a model helping at every step, and with a
human approval checkpoint standing in front of every action that cannot be taken back.

## Appendix: verification summary

The system is verified by an automated suite and by live end-to-end testing. The
agent test suite reports 36 passing and 6 environment-gated skips, and the retrieval
suite reports 6 passing. Continuous integration runs Ruff linting and both test
suites on every branch push. The retrieval evaluation records a hit rate of 0.900 and
a mean reciprocal rank of 0.800 against a 0.80 bar. The human-in-the-loop gate was
confirmed both by a deterministic worst-case test and live over a real Telegram
channel, where a send request routed by the model was held for approval and completed
only after the operator approved it.

Known limitations, stated plainly: the offline retrieval embedding is coarse, so mean
reciprocal rank can vary slightly with environment and library versions around the
0.80 bar; live-model-generated client text can violate the business style invariants
such as the no-em-dash rule and is currently caught at the human approval step rather
than prevented before it, with a deterministic post-filter identified as the fix; the
real triage classifier wrap is deferred; and hosting, multi-tenant operation, payment
and accounting integration, and additional channels are out of scope for this
submission.

# Asantico Operations Agent

A local-first operations agent for a real property-maintenance business. It runs
as a long-lived process on your own machine. You reach it from a chat app
(Telegram or email), send a plain message like "VEER LOFTS
208 had a leak, log it and draft the estimate," and it does the operational work:
triages the job, prices it with the correct Seattle tax, drafts the client
message, and answers policy questions from a grounded knowledge base. Anything
that spends money or contacts a real client stops for your approval first.

This is the OpenClaw pattern (persistent agent, tools, channels, approval
policies) aimed at one real domain instead of being general purpose, and it
reuses code that already exists: the asantico-cli tax and PDF engine, the
asantico-copilot LangGraph approval gate, and the knowledge-rag LlamaIndex
pipeline (now the knowledge_base tool).

## Run the offline demo (no keys, no dependencies)

```
python -m src.gateway          # starts the local CLI channel
```

Then type, for example:

```
What is the sales tax rate and how should invoices be addressed?
VEER LOFTS unit 208 has a water leak under the sink
create an estimate for VEER LOFTS unit 208 for $420
draft a message to Saniya
send an update to Saniya        -> stops for approval
approve                          -> only now does it send
```

Run the tests:

```
python -m pytest tests/ -q
```

## Architecture

A channel-agnostic gateway runs the agent loop. The loop routes each message to
one tool, checks it against the approval policy, and either runs it or pauses for
your approval. See `docs/architecture-diagram.svg`.

Channels (`src/channels/`) all implement one tiny interface: yield inbound
messages, send replies. The CLI channel is fully working offline; Telegram,
email, and WhatsApp are stubs with setup notes, ordered easiest to hardest.

Tools (`src/tools/`) are the agent's capabilities: knowledge_base (grounded RAG),
triage_work_order, compute_tax, generate_estimate, generate_invoice,
draft_client_message, query_jobs, and the two gated actions finalize_invoice and
send_client_message. In production each wraps the real asantico-cli; here they are
functional stubs so the whole system runs end to end.

The knowledge_base tool has two backends, chosen by `KB_BACKEND`. The default
`offline` backend is a zero-dependency hash retriever so the demo and tests run
with no install and no keys; `rag` uses the real `knowledge-rag` LlamaIndex
pipeline. If `rag` is requested but the pipeline or its dependencies are missing,
the tool logs a warning and falls back to offline. Both return the same shape:
`{"answer": str, "sources": [{"source", "text", "score"}]}`.

The router (`src/agent/router.py`) maps a message to a tool. The offline version
is deterministic keyword routing so the demo needs no keys; production swaps in an
LLM function-calling router behind the same interface.

The policy (`src/policy.py`) is the safety spine. Each tool has a risk class:
reads run freely, drafts produce documents without sending, and gated actions
(send a message, finalize an invoice) require explicit approval. Unregistered
tools are denied. This is the responsible-AI core: the agent can draft all day,
but it cannot touch money or a client without a human saying yes.

## Why local-first and why approval gates

The business is real, the clients (Saniya, Andrew) are real, and the dollars are
real. Running on your own machine keeps client and tenant data off third-party
servers, and the approval gate means an LLM mistake can never silently send a
wrong invoice or an awkward email. Tenant names never appear on documents and
client emails never state amounts, matching the existing Asantico rules.

## Channel reality check (read before building channels)

Telegram is the right first channel: the Bot API is free, needs no business
verification, and polls fine from a home machine. Email is second: poll IMAP,
reply over SMTP with an app password. WhatsApp is deferred and out of scope for this project: the
official Business Cloud API needs a verified Meta business, a registered number,
and approved templates, which is too much overhead for now.

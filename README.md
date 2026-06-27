# Asantico Operations

An operations platform for a real Seattle property-maintenance business. A single
operator sends a plain-language message from a chat app and the system triages work
orders, prices estimates and invoices with the correct Seattle tax, drafts client
messages, and answers policy questions from the business's own documents. Every
action that spends money, finalizes a document, or contacts a client stops for human
approval first.

The whole system runs locally and is reproducible offline with no API keys: the
router and the knowledge pipeline each have a dependency-free offline backend, so the
agent, the tests, and the demo all run on a bare machine. A real model and a live
Telegram channel are optional upgrades, enabled by environment variables.

It has two parts: `ops-agent` (the product surface and safety logic) and
`knowledge-rag` (the retrieval engine behind the agent's knowledge tool).

## Setup

Requires Python 3.11 or newer.

```
python -m venv .venv
source .venv/bin/activate
pip install -r ops-agent/requirements.txt
pip install -r knowledge-rag/requirements.txt
```

The core system needs nothing further. Two optional upgrades are enabled with
environment variables, kept in a local `ops-agent/.env` file that is never committed:

```
ANTHROPIC_API_KEY=...     # enables the LLM router and grounded answers
TELEGRAM_BOT_TOKEN=...    # enables the live Telegram channel (from @BotFather)
```

Load them into your shell before running with `set -a; source ops-agent/.env; set +a`.

## Run

Local CLI demo, no keys, gated actions ask for approval:

```
cd ops-agent
python -m src.gateway
```

Type a request such as `what's our sales tax`, or `send Saniya an update that the
Veer Lofts job is done` (which will stop and ask you to approve before sending), then
`quit`.

With the real model and the real retrieval pipeline:

```
ROUTER_BACKEND=llm KB_BACKEND=rag python -m src.gateway
```

Live Telegram channel (after setting the token, and on macOS setting the certificate
path once so HTTPS verification succeeds):

```
export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")
ROUTER_BACKEND=llm python -m src.gateway telegram
```

Then message your bot from your phone. The same approval gate applies, isolated per
chat.

Tests and retrieval evaluation:

```
cd ops-agent && python -m pytest tests/ -q
cd knowledge-rag && python -m knowledge_rag.ingest && python -m knowledge_rag.evaluate
```

Current retrieval metrics on the ten-question fixed set: hit rate 0.900, mean
reciprocal rank 0.800 (against a 0.80 bar), with per-query failure analysis written to
`knowledge-rag/eval/evaluation_report.md`.

## Runtime switches

Behavior is configured through the environment, so the same code runs everywhere:

- `ROUTER_BACKEND` selects the router: `keyword` (default, deterministic, no key) or
  `llm` (Anthropic function calling; falls back to keyword on no key or error).
- `KB_BACKEND` selects retrieval: `offline` (default, dependency-free hash embedding)
  or `rag` (the real LlamaIndex pipeline; falls back to offline if unavailable).
- `KB_GROUNDED` controls grounded answer generation; set to `0` to force raw snippets.
- `ANTHROPIC_MODEL` overrides the model; the default is `claude-sonnet-4-6`.
- `TELEGRAM_BOT_TOKEN` enables the Telegram channel; read from the environment only.

## Architecture summary

A channel receives a message and returns the reply; CLI and Telegram are implemented
and verified, with email and WhatsApp stubbed for future work. The gateway wires a
channel to the agent.

The agent loop keeps state per conversation so a gated action can pause for approval
and resume on the next message. Each message is resolved against any pending approval,
guarded against stray control words, routed to a tool, checked by the policy gate, and
then either executed or held for approval.

The router has two interchangeable backends behind one interface (keyword default, LLM
optional), both returning the same tool-call shape so the loop and the gate are
unaware of which ran.

The policy gate (`ops-agent/src/policy.py`) is the safety spine. It classifies every
tool as READ (no side effects, runs freely), DRAFT (produces a document or message but
does not send or finalize), or GATED (spends money, finalizes, or contacts a client,
and requires explicit approval). The two gated tools are sending a client message and
finalizing an invoice. The gate sits after routing, so the guarantee holds even if the
model misroutes.

The tool registry wraps the business's real engines: the tax computation and ReportLab
PDF generation come from the company's command-line tool, with offline fallbacks. The
knowledge tool is backed by the `knowledge-rag` pipeline. An MCP server exposes the same
tools over the Model Context Protocol. Observability writes structured, trace-correlated
log lines for every step, which is how the safety behavior is audited.

The two parts fit together as surface and engine: `ops-agent` is what the operator
talks to, and `knowledge-rag` is the production retrieval pipeline behind its knowledge
tool. The agent reuses proven Asantico code rather than reinventing it.

## Operations and quality

- `.github/workflows/ci.yml` runs Ruff lint and both test suites on every branch push.
- `ops-agent/src/mcp_server.py` exposes the tools over MCP with the gate enforced.
- `ops-agent/src/observability.py` writes structured trace-correlated logs.
- Project documents: `ops-agent/SPEC.md`, `RISKS.md`, `ENVIRONMENT.md`, `DEMO.md`, and
  the Week 10 technical report under `docs/week10/`.

## Known limitations

The offline retrieval embedding is coarse, so mean reciprocal rank can vary slightly
with environment and library versions around the 0.80 bar. Live-model-generated client
text can violate the business style invariants (for example the no-em-dash rule) and is
currently caught at the human approval step rather than prevented beforehand; a
deterministic post-filter is the planned fix. The real triage classifier wrap is
deferred. Hosting, multi-tenant operation, payment and accounting integration, and the
email and WhatsApp channels are out of scope for this submission.

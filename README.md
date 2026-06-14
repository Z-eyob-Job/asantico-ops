# Asantico Operations

An operations platform for a real property-maintenance business. It has two parts
that work together, both reproducible offline with no API keys.

## ops-agent

A local-first operations agent in the OpenClaw mold. It runs as a long-lived
process on your own machine; you reach it from a chat app (Telegram or email),
send a plain-language request, and it triages work orders, prices estimates and
invoices with the correct Seattle tax, drafts client messages, and answers policy
questions. Every action that spends money or contacts a client stops for your
approval first. See `ops-agent/README.md`.

```
cd ops-agent
python -m src.gateway        # local CLI demo, no keys; gated actions ask for approval
python -m pytest tests/ -q
```

## knowledge-rag

The grounded knowledge subsystem: a LlamaIndex retrieval pipeline over the
Asantico knowledge base (policies, tax rules, billing workflow, client accounts,
work-order intake, service trades). It powers the agent's `knowledge_base` tool
and ships with a fixed evaluation set. See `knowledge-rag/README.md`.

```
cd knowledge-rag
pip install -r requirements.txt
python -m src.ingest
python -m src.evaluate       # writes eval/evaluation_report.md
```

Current retrieval metrics on the ten-question fixed set with the offline backend:
hit rate 0.900, MRR 0.850, with per-query failure analysis.

## How the two fit

The agent is the product surface; the knowledge-rag pipeline is the production
retrieval engine behind its `knowledge_base` tool. The agent reuses existing
Asantico code (the asantico-cli tax and PDF engine, the asantico-copilot approval
gate) so it composes proven parts rather than reinventing them. Channels are CLI,
Telegram, and email; WhatsApp is deferred. Architecture diagrams are in each
part's `docs/` folder.

## Operations and quality

- `pyproject.toml` + `uv` for a reproducible environment; `uv sync` then `uv run pytest`.
- `.github/workflows/ci.yml` runs Ruff lint and both test suites on every push.
- `.mcp.json` + `ops-agent/src/mcp_server.py` expose the tools over MCP (gate enforced).
- `ops-agent/src/observability.py` writes structured trace-correlated logs.
- `SPEC.md` (constitution, spec, plan, tasks), `RISKS.md`, `ENVIRONMENT.md`, `DEMO.md`.

# CLAUDE.md - Project Context and Conventions

## What this is
Asantico Operations: a local-first operations agent (`ops-agent/`) plus a LlamaIndex
knowledge RAG subsystem (`knowledge-rag/`). The agent reaches users over chat
channels, runs operational tools, and gates every money or client action behind
human approval.

## Golden rules
- The approval policy in `ops-agent/src/policy.py` is the safety spine. Any new tool
  MUST be registered there with a risk class (read / draft / gated). Unregistered
  tools are denied. Never weaken or bypass the gate.
- Reads and drafts run freely; sends and finalizations require explicit approval.
- Every agent step emits a structured event via `ops-agent/src/observability.py`.
  Any new side-effecting path must log an event.
- Business invariants (enforced in the tool layer): Seattle tax 10.55% on every line
  item including labor; the company name is "Asantico" (never "Asantico LLC"); no
  tenant names on documents; client messages never state a dollar amount; no em dashes.

## Layout
- `ops-agent/src/gateway.py` - entrypoint; wires a channel to the agent loop
- `ops-agent/src/agent/` - loop (human-in-the-loop state) and router
- `ops-agent/src/tools/` - registry + domain tools (wrap the real asantico-cli in production)
- `ops-agent/src/policy.py` - approval gate
- `ops-agent/src/observability.py` - structured JSON logging
- `ops-agent/src/mcp_server.py` - exposes tools over MCP (stdio)
- `knowledge-rag/knowledge_rag/` - the RAG pipeline behind the knowledge_base tool
  (importable as `knowledge_rag`; selected at runtime via `KB_BACKEND=rag`)

## Commands
- Run the agent demo: `cd ops-agent && python -m src.gateway`
- Run the MCP server: `cd ops-agent && python -m src.mcp_server`
- Tests: `pytest` from each component folder
- Lint/format: `ruff check .` and `ruff format .`

## Conventions
- Python >= 3.11, managed with `uv`. Run modules as `python -m src.<module>` from the
  component folder so relative imports resolve.
- Keep changes small and reviewable, one focused branch at a time.
- The safety gate, the observability logging, and the business invariants are not
  optional and must hold across every change.

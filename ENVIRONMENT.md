# Environment Setup Notes

Reproducible setup for every contributor and for CI. Python 3.11+, managed with uv.

## uv

```
# install uv once: https://docs.astral.sh/uv/
uv sync                      # creates .venv and installs from pyproject.toml + lock
uv run pytest                # run the full suite in the managed env
```

`pyproject.toml` pins the runtime deps (mcp, llama-index-core==0.14.22) and a dev
group (pytest, ruff). Commit `uv.lock` so every machine resolves identically.

## Project conventions

Golden rules for the project: the safety gate is absolute, new tools must be
registered in the policy with a risk class, every side effect must be logged, and
the business invariants hold (10.55% tax on every line item including labor, the
name "Asantico" never "Asantico LLC", no tenant names on documents, no dollar
amounts in client messages, no em dashes).

## MCP

The agent's tools are exposed over the Model Context Protocol so any MCP host can
use them. Config is in `.mcp.json`:

```
python -m src.mcp_server        # from ops-agent/, speaks MCP over stdio
npx @modelcontextprotocol/inspector python -m src.mcp_server   # inspect/debug
```

Gated tools are advertised but refuse to run without approve=true, so the protocol
surface cannot bypass the approval gate. Transport is stdio (local); a Streamable
HTTP transport with OAuth is the path to remote use.

## CI

`.github/workflows/ci.yml` runs on every push and pull request: Ruff lint, Ruff
format check, then pytest for both `knowledge-rag` and `ops-agent`. Add the status
badge from the repo Actions tab once the first run completes.

## Logging / observability

`ops-agent/src/observability.py` writes one structured JSON line per agent step to
`logs/agent.jsonl` (and stderr unless `AGENT_LOG_STDERR=0`). Each event carries a
trace id and conversation id, so a full request is reconstructable from the log.

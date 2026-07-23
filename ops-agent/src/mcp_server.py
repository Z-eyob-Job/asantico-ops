"""MCP server: exposes the Asantico tool registry over the Model Context Protocol.

Any MCP host can connect over stdio,
call tools/list to discover the tools, and tools/call to run them. The approval
policy is enforced here too: gated tools (send a message, finalize an invoice)
are advertised but refuse to execute through MCP without an explicit
approve=true argument, so the protocol surface cannot bypass the safety gate.

Run:
    python -m src.mcp_server        # speaks MCP over stdio

Inspect with the MCP Inspector:
    npx @modelcontextprotocol/inspector python -m src.mcp_server
"""

from __future__ import annotations

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from src import policy
from src.observability import log_event, new_trace_id
from src.tools import registry

server = Server("asantico-ops")

# JSON Schemas for each tool's arguments (the inputSchema MCP clients receive).
TOOL_SCHEMAS: dict[str, dict] = {
    "knowledge_base": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Question to answer from the Asantico knowledge base."}},
        "required": ["query"],
    },
    "load_work_order": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path to an exported work-order file (.pdf or .txt) on this machine."}},
        "required": ["path"],
    },
    "fetch_email_work_order": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Optional filter that must appear in the subject or attachment name."}},
    },
    "compute_tax": {
        "type": "object",
        "properties": {"subtotal": {"type": "number", "description": "Pre-tax amount."}},
        "required": ["subtotal"],
    },
    "triage_work_order": {
        "type": "object",
        "properties": {"description": {"type": "string", "description": "The work-order description."}},
        "required": ["description"],
    },
    "generate_estimate": {
        "type": "object",
        "properties": {
            "property": {"type": "string"}, "unit": {"type": "string"},
            "line_items": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["property", "unit", "line_items"],
    },
    "generate_invoice": {
        "type": "object",
        "properties": {
            "property": {"type": "string"}, "unit": {"type": "string"},
            "line_items": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["property", "unit", "line_items"],
    },
    "draft_client_message": {
        "type": "object",
        "properties": {"manager": {"type": "string"}, "subject": {"type": "string"}},
        "required": ["manager", "subject"],
    },
    "query_jobs": {
        "type": "object",
        "properties": {"property": {"type": "string"}},
    },
    "finalize_invoice": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "approve": {"type": "boolean", "description": "Must be true; gated action."},
        },
        "required": ["invoice_id"],
    },
    "send_client_message": {
        "type": "object",
        "properties": {
            "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"},
            "approve": {"type": "boolean", "description": "Must be true; gated action."},
        },
        "required": ["to", "subject", "body"],
    },
}

TOOL_TITLES = {
    "knowledge_base": "Knowledge base",
    "load_work_order": "Load work order (parse a checklist export)",
    "fetch_email_work_order": "Fetch work order from email (IMAP)",
    "compute_tax": "Compute Seattle tax",
    "triage_work_order": "Triage work order",
    "generate_estimate": "Generate estimate (draft)",
    "generate_invoice": "Generate invoice (draft)",
    "draft_client_message": "Draft client message",
    "query_jobs": "Query jobs",
    "finalize_invoice": "Finalize invoice (gated)",
    "send_client_message": "Send client message (gated)",
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    tools = []
    for name in registry.REGISTRY:
        risk = policy.risk_of(name).value
        desc = f"[{risk}] {TOOL_TITLES.get(name, name)}."
        if risk == "gated":
            desc += " Requires approve=true to execute."
        tools.append(types.Tool(
            name=name,
            title=TOOL_TITLES.get(name, name),
            description=desc,
            inputSchema=TOOL_SCHEMAS.get(name, {"type": "object"}),
        ))
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    trace_id = new_trace_id()
    log_event("mcp_tool_call", conv_id="mcp", trace_id=trace_id, tool=name, args=arguments)

    # Enforce the approval gate at the protocol boundary.
    if policy.needs_approval(name) and not arguments.pop("approve", False):
        log_event("mcp_gated_blocked", conv_id="mcp", trace_id=trace_id, tool=name)
        return [types.TextContent(
            type="text",
            text=f"BLOCKED: '{name}' is a gated action and needs approve=true. Nothing was done.",
        )]
    arguments.pop("approve", None)

    try:
        result = registry.call(name, **arguments)
        log_event("mcp_tool_result", conv_id="mcp", trace_id=trace_id, tool=name)
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as exc:  # surfaced to the client as an error result
        log_event("mcp_tool_error", conv_id="mcp", trace_id=trace_id, tool=name, error=str(exc))
        return [types.TextContent(type="text", text=f"ERROR: {exc}")]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

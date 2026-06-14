"""Tests for the MCP server surface and structured logging."""
import asyncio
import json

from src import mcp_server, observability


def test_mcp_lists_all_registered_tools():
    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "knowledge_base" in names
    assert "send_client_message" in names
    assert len(names) == 9


def test_mcp_gated_tool_blocked_without_approval():
    out = asyncio.run(mcp_server.call_tool(
        "send_client_message", {"to": "Saniya", "subject": "x", "body": "y"}))
    assert "BLOCKED" in out[0].text


def test_mcp_gated_tool_runs_with_approval():
    out = asyncio.run(mcp_server.call_tool(
        "send_client_message", {"to": "Saniya", "subject": "x", "body": "y", "approve": True}))
    assert "sent" in out[0].text.lower()


def test_mcp_read_tool_runs_freely():
    out = asyncio.run(mcp_server.call_tool("compute_tax", {"subtotal": 420}))
    assert "464.31" in out[0].text


def test_log_event_writes_jsonl(tmp_path, monkeypatch):
    logfile = tmp_path / "t.jsonl"
    monkeypatch.setattr(observability, "LOG_FILE", str(logfile))
    monkeypatch.setattr(observability, "LOG_TO_STDERR", False)
    rec = observability.log_event("unit_test", "c1", "trace1", tool="x")
    assert rec["event"] == "unit_test"
    written = json.loads(logfile.read_text().strip())
    assert written["trace_id"] == "trace1" and written["tool"] == "x"

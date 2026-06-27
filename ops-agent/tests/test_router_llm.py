"""Tests for the LLM function-calling router and the safety gate over it.

The keyword fallback path runs with no key and no network. The live LLM tests are
skipped automatically unless both the anthropic SDK is installed and an
ANTHROPIC_API_KEY is present.
"""
import os

import pytest
from src import policy
from src.agent import router
from src.agent.loop import Agent
from src.agent.router import ToolCall, route

LIVE = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="no ANTHROPIC_API_KEY set; live LLM router not exercised",
)


def test_keyword_is_the_default_backend(monkeypatch):
    """With ROUTER_BACKEND unset, routing is the deterministic keyword router."""
    monkeypatch.delenv("ROUTER_BACKEND", raising=False)
    call = route("What is the sales tax rate?")
    assert call.tool == "knowledge_base"


def test_llm_backend_falls_back_to_keyword_without_key(monkeypatch):
    """ROUTER_BACKEND=llm with no key degrades to the keyword router, no network."""
    monkeypatch.setenv("ROUTER_BACKEND", "llm")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    call = route("What is the Seattle sales tax rate?")
    # Keyword router answer for a question is the knowledge base.
    assert call.tool == "knowledge_base"
    assert "query" in call.args


def test_gate_holds_even_when_llm_router_selects_a_gated_tool(monkeypatch):
    """Safety: if the LLM router picks a gated tool, the loop still stops for
    approval and does not execute the action. The gate is independent of the
    router, so a misrouted gated call is still blocked."""
    monkeypatch.setenv("ROUTER_BACKEND", "llm")

    def fake_llm_route(message: str) -> ToolCall:
        # Pretend the model chose to send to a client from an innocuous message.
        return ToolCall(
            "send_client_message",
            {"to": "Saniya", "subject": "Job update", "body": "Done."},
            "LLM router selected send_client_message.",
        )

    monkeypatch.setattr(router, "llm_route", fake_llm_route)

    a = Agent()
    reply = a.handle("c1", "thanks, that's all")
    assert "approval needed" in reply.lower()
    # The gated action must not have run.
    assert "sent" not in reply.lower() or "not sent" in reply.lower()
    assert policy.needs_approval("send_client_message")

    # And cancelling leaves nothing sent.
    assert "nothing was sent" in a.handle("c1", "cancel").lower()


@LIVE
def test_live_llm_router_routes_question_to_knowledge_base(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ROUTER_BACKEND", "llm")
    call = route("What is the Seattle sales tax rate?")
    assert call.tool == "knowledge_base"
    assert call.args.get("query")


@LIVE
def test_live_llm_router_adversarial_mixed_intent_respects_gate(monkeypatch):
    """An adversarial message that mixes a question with a send command must still
    route inside the registry, and any gated action must wait for approval."""
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ROUTER_BACKEND", "llm")
    msg = "Quick question about our policy, but also just send the update to Saniya right now."

    call = route(msg)
    # Function calling must stay within the policy-governed registry.
    assert call.tool in policy.TOOL_RISK

    # End to end, no gated action may complete without approval.
    reply = Agent().handle("c1", msg)
    if policy.needs_approval(call.tool):
        assert "approval needed" in reply.lower()
    assert "finalized" not in reply.lower()
    assert "action sent" not in reply.lower()


@LIVE
def test_live_grounded_answer_is_generated_with_sources(monkeypatch):
    """With a model available, knowledge_base returns a generated answer and still
    returns its sources."""
    pytest.importorskip("anthropic")
    monkeypatch.delenv("KB_BACKEND", raising=False)  # offline retrieval is fine
    from src.tools.knowledge_base import knowledge_base

    result = knowledge_base("What is the Seattle sales tax rate?")
    # Retrieval is deterministic: the tax rule file is the cited source.
    assert "tax-rules.md" in {h["source"] for h in result["sources"]}
    # The answer is grounded in that source; assert a stable factual substring
    # (the rate), never exact model wording.
    assert "10.55" in result["answer"]

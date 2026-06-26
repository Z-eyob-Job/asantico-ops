"""Tests for the safety-critical paths: routing, the approval gate, tax math."""
from src import policy
from src.agent.loop import Agent


def test_send_requires_approval():
    a = Agent()
    r = a.handle("c1", "send an update to Saniya")
    assert "approval needed" in r.lower()


def test_approve_executes_gated_action():
    a = Agent()
    a.handle("c1", "send an update to Saniya")
    r = a.handle("c1", "approve")
    assert "sent" in r.lower()


def test_cancel_blocks_gated_action():
    a = Agent()
    a.handle("c1", "send an update to Saniya")
    r = a.handle("c1", "cancel")
    assert "nothing was sent" in r.lower()


def test_question_routes_to_knowledge_base():
    a = Agent()
    r = a.handle("c1", "What is the sales tax rate?")
    assert "10.55" in r and "sources" in r.lower()


def test_emergency_is_escalated():
    a = Agent()
    r = a.handle("c1", "there is a water leak under the sink")
    assert "emergency" in r.lower() and "escalat" in r.lower()


def test_tax_rate_is_seattle():
    from src.tools.domain import compute_tax
    out = compute_tax(420.0)
    assert out["tax"] == 44.31 and out["total"] == 464.31


def test_reads_never_gated_sends_always_gated():
    assert not policy.needs_approval("knowledge_base")
    assert not policy.needs_approval("generate_estimate")
    assert policy.needs_approval("send_client_message")
    assert policy.needs_approval("finalize_invoice")


def test_send_carries_the_reviewed_draft():
    """A send must use the exact message the operator drafted and reviewed,
    not a generic placeholder. This protects the gated client-contact path."""
    a = Agent()
    draft = a.handle("c1", "draft a message to Saniya")
    assert "saniya" in draft.lower()
    prompt = a.handle("c1", "send an update to Saniya")
    # The approval prompt should show the drafted body, not a generic one.
    assert "ready for your review" in prompt.lower()
    assert "work completed; documentation ready for review" not in prompt.lower()


def test_unregistered_tool_is_blocked():
    import pytest
    with pytest.raises(PermissionError):
        policy.risk_of("rm_rf_everything")

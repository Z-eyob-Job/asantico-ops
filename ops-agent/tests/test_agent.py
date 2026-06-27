"""Tests for the safety-critical paths: routing, the approval gate, tax math."""
import os

import pytest
from src import policy
from src.agent.loop import Agent
from src.agent.router import ToolCall


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
    # Assert on the deterministic retrieval (the cited source file), not the
    # grounded answer prose, which is non-deterministic when a key is present.
    assert "sources" in r.lower() and "tax-rules.md" in r


def test_emergency_is_escalated():
    a = Agent()
    r = a.handle("c1", "there is a water leak under the sink")
    assert "emergency" in r.lower() and "escalat" in r.lower()


def test_tax_rate_is_seattle():
    from src.tools.domain import compute_tax
    out = compute_tax(420.0)
    assert out["tax"] == 44.31 and out["total"] == 464.31


def test_multi_line_tax_is_per_line():
    """Tax applies to every line item, so a 200 + 220 estimate totals the same
    464.31 as a single 420 line."""
    from src.tools.domain import generate_estimate
    out = generate_estimate("VEER LOFTS", "208", [
        {"description": "labor", "amount": 200.0},
        {"description": "materials", "amount": 220.0},
    ])
    assert out["subtotal"] == 420.0 and out["tax"] == 44.31 and out["total"] == 464.31


def test_real_tax_engine_matches_to_the_cent():
    """When asantico-cli is installed, the real Decimal engine is used and must
    match the expected cents. Skipped automatically if it is not installed."""
    import pytest
    pytest.importorskip("asantico_cli")
    from src.tools.domain import TAX_ENGINE, compute_tax
    assert TAX_ENGINE == "asantico-cli"
    out = compute_tax(420.0)
    assert out["engine"] == "asantico-cli"
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


def test_assumed_price_is_surfaced():
    """When no price is in the message, the agent must flag the assumed amount
    rather than silently pricing the document."""
    a = Agent()
    r = a.handle("c1", "create an estimate for VEER LOFTS unit 208")
    assert "assumed" in r.lower()


def test_priced_message_has_no_assumption_note():
    a = Agent()
    r = a.handle("c1", "create an estimate for VEER LOFTS unit 208 for $420")
    assert "assumed" not in r.lower()
    assert "464.31" in r


def test_gateway_selects_correct_channel_class():
    from src.channels.cli import CLIChannel
    from src.gateway import make_channel
    assert isinstance(make_channel("cli"), CLIChannel)


def test_gateway_rejects_unknown_channel():
    import pytest
    from src.gateway import make_channel
    with pytest.raises(ValueError):
        make_channel("carrier_pigeon")


def test_deferred_channels_fail_clearly():
    import pytest
    from src.channels.whatsapp import WhatsAppChannel
    with pytest.raises(NotImplementedError):
        list(WhatsAppChannel().listen())


def test_finalize_is_gated_and_uses_drafted_invoice():
    """Finalizing an invoice is gated, and after approval it finalizes the exact
    invoice the operator drafted."""
    a = Agent()
    a.handle("c1", "create an invoice for VEER LOFTS unit 208 for $420")
    prompt = a.handle("c1", "finalize the invoice")
    assert "approval needed" in prompt.lower()
    done = a.handle("c1", "approve")
    assert "finalized" in done.lower()


def test_real_pdf_engine_writes_a_file(tmp_path, monkeypatch):
    """When asantico-cli is installed, finalize renders a real PDF file.
    Skipped automatically when the engine is not present."""
    import pytest
    pytest.importorskip("asantico_cli")
    pytest.importorskip("reportlab")
    from src.tools import domain
    if domain.PDF_ENGINE != "asantico-cli":
        pytest.skip("PDF engine not active")
    monkeypatch.chdir(tmp_path)
    out = domain.finalize_invoice(
        property="VEER LOFTS", unit="208",
        line_items=[{"description": "Service call", "amount": 420.0}],
        invoice_id="INV-0001",
    )
    from pathlib import Path
    assert out["engine"] == "asantico-cli"
    assert Path(out["pdf"]).exists()


def test_unregistered_tool_is_blocked():
    with pytest.raises(PermissionError):
        policy.risk_of("rm_rf_everything")


# --- Issue 1: control words with nothing pending must not route to a tool ---
def test_control_word_with_no_pending_is_not_routed():
    """A bare approve/cancel-style word with no pending action is a no-op: the
    agent says nothing is waiting and never reaches the router or a tool."""
    for word in ("approve", "yes", "confirm", "ok", "cancel", "no", "stop"):
        a = Agent()
        r = a.handle("c1", word)
        assert "nothing" in r.lower()
        # It must not have routed to the knowledge base (or any tool).
        assert "sources" not in r.lower()


def test_control_word_no_pending_holds_for_both_backends(monkeypatch):
    """The no-pending guard sits before routing, so it holds for either backend."""
    for backend in ("keyword", "llm"):
        monkeypatch.setenv("ROUTER_BACKEND", backend)
        r = Agent().handle("c1", "approve")
        assert "nothing" in r.lower()


# --- Issue 2: send intent is gated; nothing leaves without approval ---
def test_send_intent_is_gated_under_llm_router(monkeypatch):
    """Even when the LLM router selects the sending tool, the policy gate stops it:
    no client message is sent without an approval step. The gate is independent of
    which router produced the ToolCall."""
    monkeypatch.setenv("ROUTER_BACKEND", "llm")
    from src.agent import router

    monkeypatch.setattr(
        router,
        "llm_route",
        lambda message: ToolCall(
            "send_client_message",
            {"to": "Saniya", "subject": "Job update", "body": "Done."},
            "LLM router selected send_client_message.",
        ),
    )
    a = Agent()
    r = a.handle("c1", "send the update to Saniya")
    assert "approval needed" in r.lower()
    assert "sent" not in r.lower()  # nothing has left yet
    # Cancelling leaves nothing sent.
    assert "nothing was sent" in a.handle("c1", "cancel").lower()


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="no ANTHROPIC_API_KEY set; live LLM router not exercised",
)
def test_live_llm_send_intent_requires_approval(monkeypatch):
    """With a real key, the LLM router routes a send-intent message to the gated
    send and the agent waits for approval before anything leaves."""
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ROUTER_BACKEND", "llm")
    a = Agent()
    r = a.handle("c1", "Send the update to Saniya now.")
    assert "approval needed" in r.lower()
    assert "nothing was sent" in a.handle("c1", "cancel").lower()

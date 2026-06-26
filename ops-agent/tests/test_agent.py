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


def test_unregistered_tool_is_blocked():
    import pytest
    with pytest.raises(PermissionError):
        policy.risk_of("rm_rf_everything")

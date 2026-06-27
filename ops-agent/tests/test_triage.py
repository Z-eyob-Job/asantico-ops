"""Tests for triage_work_order: the deterministic offline path and the real
asantico-cli escalation rule. Everything here runs with no key; the real-engine
test is skipped automatically when asantico-cli is not installed."""
import pytest
from src.tools import domain


def test_offline_triage_classifies_leak_as_plumbing_emergency(monkeypatch):
    """The default offline path classifies a leak as a plumbing emergency and
    escalates, with no install and no key."""
    monkeypatch.delenv("TRIAGE_ENGINE", raising=False)  # default is offline
    out = domain.triage_work_order("there is a water leak under the sink")
    assert out["urgency"] == "emergency"
    assert out["trade"] == "plumbing"
    assert out["escalate"] is True
    assert set(out) == {"urgency", "trade", "escalate", "note"}  # shape unchanged


def test_real_engine_uses_should_escalate_rule(monkeypatch):
    """When asantico-cli is installed, the real should_escalate rule drives the
    escalation decision (emergencies and low-confidence cases escalate). No key is
    used, so classification is the keyword fallback. Skipped automatically when
    asantico-cli is not installed."""
    pytest.importorskip("asantico_cli")
    monkeypatch.setenv("TRIAGE_ENGINE", "real")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # no key -> keyword classify
    assert domain.TRIAGE_RULE == "asantico-cli"

    # Emergency escalates via the real rule's urgency branch.
    emergency = domain.triage_work_order("there is a gas leak in the kitchen")
    assert emergency["urgency"] == "emergency"
    assert emergency["escalate"] is True

    # An undetermined trade is low confidence, so the real rule's confidence
    # branch escalates it, something the offline built-in rule would NOT do.
    uncertain = domain.triage_work_order("something seems off in the apartment")
    assert uncertain["urgency"] == "routine"
    assert uncertain["trade"] == "general"
    assert uncertain["escalate"] is True

    # Contrast: the offline engine does not escalate that same uncertain case,
    # proving the real should_escalate rule is what changed the outcome.
    monkeypatch.setenv("TRIAGE_ENGINE", "offline")
    assert domain.triage_work_order("something seems off in the apartment")["escalate"] is False

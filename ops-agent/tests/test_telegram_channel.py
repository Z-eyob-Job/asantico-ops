"""Tests for the Telegram channel and per-chat approval isolation.

Everything here runs with NO token and NO network: construction is checked with a
dummy token (set via monkeypatch, no API call is made at construction) and with the
token absent, the chat_id -> conv_id mapping is checked on a synthetic update, and
per-chat isolation is exercised at the Agent level with two conv_ids.
"""
import pytest
from src.agent.loop import Agent
from src.channels.cli import CLIChannel
from src.channels.telegram import TelegramChannel
from src.gateway import make_channel


def test_gateway_selects_telegram_channel(monkeypatch):
    """The gateway returns a TelegramChannel for 'telegram'. A dummy token lets
    construction succeed without any network call."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-token-not-real")
    channel = make_channel("telegram")
    assert isinstance(channel, TelegramChannel)
    assert channel.name == "telegram"


def test_gateway_defaults_to_cli():
    assert isinstance(make_channel("cli"), CLIChannel)


def test_missing_token_raises_clear_error(monkeypatch):
    """With no token, construction fails with a clear, token-named message."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        TelegramChannel()
    assert "TELEGRAM_BOT_TOKEN" in str(excinfo.value)


def test_chat_id_maps_to_conv_id(monkeypatch):
    """A Telegram update becomes an Inbound whose conv_id is the chat_id as a
    string, which is what makes approval state per chat. No network."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")
    channel = make_channel("telegram")
    update = {
        "update_id": 7,
        "message": {"chat": {"id": 4242}, "from": {"username": "ada"}, "text": "hello"},
    }
    inbound = channel._to_inbound(update)
    assert inbound is not None
    assert inbound.conv_id == "4242"  # the chat_id, as a string
    assert inbound.text == "hello"
    assert inbound.sender == "ada"


def test_non_text_update_is_ignored(monkeypatch):
    """Updates without text (stickers, joins) are dropped, not crashed on."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")
    channel = make_channel("telegram")
    assert channel._to_inbound({"update_id": 1, "message": {"chat": {"id": 5}}}) is None
    assert channel._to_inbound({"update_id": 2}) is None


def test_per_chat_approval_isolation():
    """A pending gated action in chat A is not resolved by an approve from chat B;
    approving in chat A completes only A's action. Exercised at the Agent level
    with two conv_ids (the Telegram chat_ids), so it needs no Telegram API."""
    agent = Agent()
    chat_a, chat_b = "1001", "2002"  # two distinct Telegram chat_ids

    # Chat A starts a gated send; it must pause for approval.
    prompt_a = agent.handle(chat_a, "send an update to Saniya")
    assert "approval needed" in prompt_a.lower()

    # An approve from chat B must NOT resolve chat A's pending action: chat B has
    # nothing pending of its own, and state is keyed per conv_id.
    reply_b = agent.handle(chat_b, "approve")
    assert "sent" not in reply_b.lower()
    assert "nothing waiting" in reply_b.lower()

    # Chat A's action is still pending; approving in chat A completes only A's.
    done_a = agent.handle(chat_a, "approve")
    assert "sent" in done_a.lower()

    # Chat A is now clear too: a second approve in A finds nothing pending.
    assert "nothing waiting" in agent.handle(chat_a, "approve").lower()

"""Telegram channel: a long-polling Bot API client built on the standard library.

Telegram is the recommended first real channel: the Bot API is free, needs no
business verification, and getUpdates long-polling works from a home machine
behind NAT with no public URL. This uses only the stdlib (urllib + json), so the
channel adds no dependency and the test suite runs with no token and no network.

conv_id is the Telegram chat_id, so the agent loop keys approval state per chat: a
gated action started in one chat can only be approved from that same chat, and two
different chats keep independent pending state. The gateway, agent loop, policy
gate, and router are untouched.

Setup: talk to @BotFather, get a token, set TELEGRAM_BOT_TOKEN in the environment.
The token is read from the environment only; it is never hardcoded, logged, or
written to disk (the request URL that embeds it is never logged).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

from src.channels.base import Channel, Inbound

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
# Long-poll seconds: getUpdates blocks server-side until a message or timeout.
POLL_TIMEOUT = int(os.getenv("TELEGRAM_POLL_TIMEOUT", "30"))


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not set. Export it (from @BotFather) to use "
                "the Telegram channel, or run the CLI channel instead."
            )
        self._offset: int | None = None  # getUpdates acknowledgement cursor

    # -- Bot API helper ----------------------------------------------------- #
    def _call(self, method: str, params: dict, timeout: float) -> dict:
        """POST to a Bot API method and return the decoded JSON. The token lives
        only in the URL, which is never logged."""
        url = _API.format(token=self.token, method=method)
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def _to_inbound(update: dict) -> Inbound | None:
        """Map a Telegram update to an Inbound, or None for updates we ignore.

        conv_id is the chat_id (as a string), which is what makes approval state
        per chat once it reaches the agent loop."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None
        text = message.get("text")
        if not text:
            return None  # ignore non-text updates (stickers, joins, photos, ...)
        chat_id = message["chat"]["id"]
        sender = str(message.get("from", {}).get("username") or chat_id)
        return Inbound(conv_id=str(chat_id), text=text, sender=sender)

    # -- Channel interface -------------------------------------------------- #
    def listen(self) -> Iterator[Inbound]:
        logger.info("Telegram channel: long-polling for updates.")
        while True:
            params: dict = {"timeout": POLL_TIMEOUT}
            if self._offset is not None:
                params["offset"] = self._offset
            try:
                payload = self._call("getUpdates", params, timeout=POLL_TIMEOUT + 10)
            except urllib.error.URLError as exc:
                # Transient network/API error: log without the token-bearing URL.
                logger.warning("getUpdates failed (%s); retrying.", exc)
                continue
            for update in payload.get("result", []):
                self._offset = update["update_id"] + 1  # ack so it is not re-fetched
                inbound = self._to_inbound(update)
                if inbound is not None:
                    yield inbound

    def send(self, conv_id: str, text: str) -> None:
        try:
            self._call("sendMessage", {"chat_id": conv_id, "text": text}, timeout=15)
        except urllib.error.URLError as exc:
            logger.warning("sendMessage to chat %s failed (%s).", conv_id, exc)

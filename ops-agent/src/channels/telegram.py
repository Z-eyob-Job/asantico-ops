"""Telegram channel (STUB). Telegram is the recommended first real channel: the
Bot API is free, needs no business verification, and long-polling works from a
home machine behind NAT. Fill in with python-telegram-bot.

Setup: talk to @BotFather, get a token, set TELEGRAM_BOT_TOKEN in .env.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from src.channels.base import Channel, Inbound


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env to use Telegram.")

    def listen(self) -> Iterator[Inbound]:
        # Production: long-poll getUpdates (or python-telegram-bot Application).
        # conv_id should be the Telegram chat_id so approval state is per chat.
        raise NotImplementedError("Wire python-telegram-bot here.")

    def send(self, conv_id: str, text: str) -> None:
        # Production: POST to https://api.telegram.org/bot<token>/sendMessage
        raise NotImplementedError("Wire sendMessage here.")

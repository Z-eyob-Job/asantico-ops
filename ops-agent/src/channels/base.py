"""Channel adapter interface. Every channel (CLI, Telegram, email, WhatsApp)
implements the same two operations: yield inbound messages and send replies.
The gateway is channel-agnostic, so adding a channel never touches the agent."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Inbound:
    conv_id: str   # stable per sender/chat, so approval state survives across messages
    text: str
    sender: str = ""


class Channel:
    name = "base"

    def listen(self) -> Iterator[Inbound]:
        raise NotImplementedError

    def send(self, conv_id: str, text: str) -> None:
        raise NotImplementedError

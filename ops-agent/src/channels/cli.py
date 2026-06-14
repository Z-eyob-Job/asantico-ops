"""Local CLI channel. Lets you talk to the agent in a terminal exactly the way a
WhatsApp/Telegram user would, with the same conv_id-keyed approval state. This is
the offline, no-keys demo surface."""

from __future__ import annotations

import sys
from collections.abc import Iterator

from src.channels.base import Channel, Inbound


class CLIChannel(Channel):
    name = "cli"

    def listen(self) -> Iterator[Inbound]:
        print("Asantico Operations Agent (CLI). Type a message, or 'quit'.\n")
        for line in sys.stdin:
            line = line.strip()
            if line.lower() in ("quit", "exit"):
                return
            if line:
                yield Inbound(conv_id="cli-user", text=line, sender="cli-user")

    def send(self, conv_id: str, text: str) -> None:
        print(f"\nagent> {text}\n")

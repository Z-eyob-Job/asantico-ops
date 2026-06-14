"""Email channel (STUB). Second-easiest real channel: poll IMAP for new mail,
reply over SMTP. conv_id = the email thread/Message-ID so approvals stay threaded.
Set EMAIL_USER / EMAIL_PASS (app password) in .env. Fill in later."""

from __future__ import annotations

import os
from collections.abc import Iterator

from src.channels.base import Channel, Inbound


class EmailChannel(Channel):
    name = "email"

    def __init__(self):
        self.user = os.getenv("EMAIL_USER")
        if not self.user:
            raise RuntimeError("Set EMAIL_USER / EMAIL_PASS in .env to use email.")

    def listen(self) -> Iterator[Inbound]:
        raise NotImplementedError("Poll IMAP for unseen messages here.")

    def send(self, conv_id: str, text: str) -> None:
        raise NotImplementedError("Send via SMTP, reply-to the thread here.")

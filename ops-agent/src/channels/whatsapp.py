"""WhatsApp channel (STUB + reality check). WhatsApp is the HARDEST channel: the
official WhatsApp Business Cloud API requires a Meta Business account, a verified
business, and a registered number, with approved message templates for
business-initiated messages. Recommended order: ship Telegram and email first,
add WhatsApp last via the Cloud API or a provider like Twilio. conv_id = the
sender's phone number."""

from __future__ import annotations

from collections.abc import Iterator

from src.channels.base import Channel, Inbound


class WhatsAppChannel(Channel):
    name = "whatsapp"

    def listen(self) -> Iterator[Inbound]:
        raise NotImplementedError("WhatsApp Business Cloud API webhook (deferred).")

    def send(self, conv_id: str, text: str) -> None:
        raise NotImplementedError("WhatsApp Cloud API /messages (deferred).")

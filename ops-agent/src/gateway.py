"""Gateway: the long-lived local process (the OpenClaw pattern).

It owns one or more channels, runs the agent loop, and routes replies back to
whoever messaged. Run it on your own machine; users reach the agent from their
chat app, and every gated action stops for your approval before it happens.

Usage:
    python -m src.gateway            # local CLI channel (offline demo, no keys)
    python -m src.gateway telegram   # Telegram (needs TELEGRAM_BOT_TOKEN)
    python -m src.gateway email       # email (needs EMAIL_USER / EMAIL_PASS)
"""

from __future__ import annotations

import sys

from src.agent.loop import Agent


def make_channel(name: str):
    if name == "cli":
        from src.channels.cli import CLIChannel
        return CLIChannel()
    if name == "telegram":
        from src.channels.telegram import TelegramChannel
        return TelegramChannel()
    if name == "email":
        from src.channels.email_channel import EmailChannel
        return EmailChannel()
    if name == "whatsapp":
        from src.channels.whatsapp import WhatsAppChannel
        return WhatsAppChannel()
    raise ValueError(f"Unknown channel: {name}")


def run(channel_name: str = "cli") -> None:
    channel = make_channel(channel_name)
    agent = Agent()
    print(f"[gateway] listening on channel: {channel.name}")
    for msg in channel.listen():
        reply = agent.handle(msg.conv_id, msg.text)
        channel.send(msg.conv_id, reply)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "cli")

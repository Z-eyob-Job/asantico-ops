"""Local CLI channel. Lets you talk to the agent in a terminal exactly the way a
WhatsApp/Telegram user would, with the same conv_id-keyed approval state. This is
the offline, no-keys demo surface.

Voice input, fully offline: type `voice <path-to-audio>` (e.g. an iPhone voice
memo AirDropped to this machine) and the file is transcribed locally with
Whisper, echoed back, and handled like any typed message. No network involved.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

from src.channels.base import Channel, Inbound


class CLIChannel(Channel):
    """Terminal channel. With SPEAK=1 on macOS, replies are also spoken aloud
    using the built-in offline `say` engine (pick a voice with SAY_VOICE, e.g.
    SAY_VOICE=Samantha). Tables and paths are skipped; only the conversational
    part is voiced, so review cards stay a visual read."""

    name = "cli"
    _speaker = None  # last `say` process, so replies do not talk over each other

    def listen(self) -> Iterator[Inbound]:
        print("Asantico Operations Agent (CLI). Type a message, 'voice <audio "
              "file>' for a voice note, or 'quit'.\n")
        for line in sys.stdin:
            line = line.strip()
            if line.lower() in ("quit", "exit"):
                return
            if line.lower().startswith("voice "):
                text = self._transcribe(line[6:].strip())
                if not text:
                    continue
                yield Inbound(conv_id="cli-user", text=text, sender="cli-user")
                continue
            if line:
                yield Inbound(conv_id="cli-user", text=line, sender="cli-user")

    @staticmethod
    def _transcribe(raw_path: str) -> str | None:
        """Transcribe a local audio file, echoing the result so the operator
        sees exactly what the agent will act on. Returns None on any problem
        (already printed) so the loop just continues."""
        path = Path(raw_path.strip("'\"")).expanduser()
        if not path.exists():
            print(f"\nagent> Audio file not found: {path}\n")
            return None
        try:
            from src import voice

            text = voice.transcribe(str(path))
        except Exception as exc:  # noqa: BLE001 - degrade with a hint, never crash
            print(f"\nagent> {exc}\n")
            return None
        if not text:
            print("\nagent> I could not hear any speech in that recording.\n")
            return None
        print(f"\n(heard: {text})")
        return text

    def send(self, conv_id: str, text: str) -> None:
        print(f"\nagent> {text}\n")
        self._speak(text)

    def _speak(self, text: str) -> None:
        import os
        import subprocess
        import sys as _sys

        if _sys.platform != "darwin" or os.getenv("SPEAK", "0") != "1":
            return
        # Voice the conversational lines only: skip table rows (indented),
        # paths, and JSON-ish content; cap length so it stays snappy.
        lines = [ln for ln in text.splitlines()
                 if ln and not ln.startswith(" ") and "/" not in ln
                 and "{" not in ln]
        speech = " ".join(lines)[:280]
        if not speech:
            return
        try:
            if self._speaker and self._speaker.poll() is None:
                self._speaker.terminate()
            cmd = ["say"]
            voice = os.getenv("SAY_VOICE")
            if voice:
                cmd += ["-v", voice]
            self._speaker = subprocess.Popen(cmd + [speech])
        except OSError:
            pass  # voice is a convenience, never an error

"""Local, offline voice transcription for the ops agent.

Field reality: operators often have no connection while working, and typing on a
phone with work gloves is slow. So voice notes are a first-class input: the audio
is transcribed ON THIS MACHINE with faster-whisper (CTranslate2 Whisper). No
cloud speech API, no key, no network at transcription time. The Whisper model
weights are fetched once on first use and cached locally; after that the whole
voice -> text -> triage -> estimate/invoice pipeline runs with zero connectivity.

Two ways audio reaches the agent:
- Telegram voice notes (src/channels/telegram.py) when there is connectivity.
- A local audio file via the CLI channel ("voice ~/memo.m4a") for the fully
  offline path: record a memo on the phone, AirDrop it to the laptop, done.

Configuration (env):
- WHISPER_MODEL: model size, default "base.en" (~74 MB; "small.en" is more
  accurate, "tiny.en" is fastest).
- WHISPER_DEVICE: "auto" uses a GPU when CTranslate2 finds one, else CPU.

The dependency is optional and lazily imported: without faster-whisper installed
the agent still runs; voice input replies with a one-line install hint instead of
crashing (the same everywhere-degrade pattern as the router and KB backends).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("WHISPER_MODEL", "base.en")
DEVICE = os.getenv("WHISPER_DEVICE", "auto")

INSTALL_HINT = ("Voice input needs the local transcriber. Install it once with: "
                "pip install faster-whisper")

_model = None  # loaded once per process; first call also downloads+caches weights


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(path: str) -> str:
    """Transcribe an audio file to text using the local Whisper model.

    Accepts anything ffmpeg/PyAV can decode: Telegram .oga voice notes, iPhone
    .m4a voice memos, .wav, .mp3. Raises RuntimeError with a friendly message
    when the optional dependency is missing.
    """
    global _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(INSTALL_HINT) from exc

    if _model is None:
        logger.info("Loading Whisper model '%s' (first call caches weights).",
                    MODEL_NAME)
        _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type="int8")

    segments, _info = _model.transcribe(str(path), vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    logger.info("Transcribed %s: %r", path, text[:120])
    return text

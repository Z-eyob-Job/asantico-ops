"""Optional Anthropic LLM access, shared by the LLM router and grounded answers.

The offline spine never imports this module's heavy dependency: ``anthropic`` is
imported lazily inside :func:`get_client`, so the keyword router and the offline
knowledge path keep running with no install and no key.

Key handling (safety): the API key is read from the environment only, by the SDK
itself (``ANTHROPIC_API_KEY``). It is never accepted as an argument, never logged,
and never written to disk.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-sonnet-4-6"


def model_name() -> str:
    """The model id to use, overridable via the ANTHROPIC_MODEL env var."""
    return os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)


def have_key() -> bool:
    """True if an Anthropic API key is present in the environment."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_client():
    """Return an Anthropic client, or raise if it cannot be used.

    Raises RuntimeError when no key is set and ImportError when the SDK is not
    installed; both are caught by callers, which then fall back to the offline
    path. The client reads the key from the environment on its own.
    """
    if not have_key():
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic

    return anthropic.Anthropic()

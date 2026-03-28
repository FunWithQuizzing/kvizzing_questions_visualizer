"""
LLM client — Groq adapter that exposes the same .messages.create() interface
as the Anthropic client so all pipeline stages work unchanged.
"""

from __future__ import annotations

import os


# ── Response shims ─────────────────────────────────────────────────────────────

class _Content:
    __slots__ = ("text",)
    def __init__(self, text: str):
        self.text = text

class _Response:
    __slots__ = ("content",)
    def __init__(self, text: str):
        self.content = [_Content(text)]

class _Messages:
    def __init__(self, create_fn):
        self._create_fn = create_fn

    def create(self, *, model: str, max_tokens: int, system: str, messages: list, **_):
        return self._create_fn(model=model, max_tokens=max_tokens, system=system, messages=messages)


# ── Groq client ────────────────────────────────────────────────────────────────

_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqClient:
    """
    Drop-in replacement for anthropic.Anthropic() using the Groq API.
    Reads GROQ_API_KEY from the environment.
    """

    def __init__(self):
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("Set GROQ_API_KEY environment variable.")
        self._client = Groq(api_key=api_key)
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, max_tokens: int, system: str, messages: list) -> _Response:
        response = self._client.chat.completions.create(
            model=_GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": messages[-1]["content"]},
            ],
        )
        return _Response(response.choices[0].message.content)


# ── Anthropic client ───────────────────────────────────────────────────────────

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


class AnthropicClient:
    """Drop-in replacement using the Anthropic API (ANTHROPIC_API_KEY)."""

    def __init__(self):
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Set ANTHROPIC_API_KEY environment variable.")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, max_tokens: int, system: str, messages: list) -> _Response:
        response = self._client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return _Response(response.content[0].text)


# ── Factory ────────────────────────────────────────────────────────────────────

def get_client():
    """Return a GroqClient or AnthropicClient, whichever key is available."""
    import logging
    log = logging.getLogger("kvizzing")
    for cls in (GroqClient, AnthropicClient):
        try:
            return cls()
        except (ImportError, RuntimeError):
            pass
    log.warning("No LLM client available: Set GROQ_API_KEY or ANTHROPIC_API_KEY.")
    return None

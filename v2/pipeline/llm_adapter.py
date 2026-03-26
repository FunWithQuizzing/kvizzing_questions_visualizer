"""
LLM adapter — wraps Groq (or Gemini) with the same .messages.create()
interface as the Anthropic client, so all pipeline stages work unchanged.

Priority order in pipeline.py:
  1. Anthropic  (ANTHROPIC_API_KEY)
  2. Groq       (GROQ_API_KEY)
  3. Gemini     (GEMINI_API_KEY / GOOGLE_API_KEY)
"""

from __future__ import annotations

import os


# ── Response shims (match anthropic response shape) ───────────────────────────

class _Content:
    __slots__ = ("text",)
    def __init__(self, text: str):
        self.text = text

class _Response:
    __slots__ = ("content",)
    def __init__(self, text: str):
        self.content = [_Content(text)]


# ── Messages namespace ─────────────────────────────────────────────────────────

class _Messages:
    def __init__(self, create_fn):
        self._create_fn = create_fn

    def create(self, *, model: str, max_tokens: int, system: str, messages: list, **_):
        return self._create_fn(model=model, max_tokens=max_tokens, system=system, messages=messages)


# ── Groq client ────────────────────────────────────────────────────────────────

_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqClient:
    """
    Drop-in replacement for anthropic.Anthropic() that calls the Groq API.
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
                {"role": "user", "content": messages[-1]["content"]},
            ],
        )
        return _Response(response.choices[0].message.content)


# ── Gemini client (fallback) ───────────────────────────────────────────────────

class GeminiClient:
    """
    Drop-in replacement for anthropic.Anthropic() that calls the Gemini API.
    Reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment.
    """

    def __init__(self):
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY environment variable.")
        self._client = genai.Client(api_key=api_key)
        self._types = types
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, max_tokens: int, system: str, messages: list) -> _Response:
        response = self._client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=messages[-1]["content"],
            config=self._types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        return _Response(response.text)

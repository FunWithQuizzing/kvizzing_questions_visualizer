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


# ── Ollama client ──────────────────────────────────────────────────────────────

_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:latest")
_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "32768"))


class OllamaClient:
    """
    Local Ollama client via its OpenAI-compatible endpoint.
    Requires the `openai` package: pip install openai
    Set OLLAMA_MODEL, OLLAMA_BASE_URL, OLLAMA_NUM_CTX env vars to override defaults.
    """

    def __init__(self):
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package required for OllamaClient: pip install openai")
        self._openai = openai
        self._client = openai.OpenAI(
            base_url=_OLLAMA_BASE_URL,
            api_key="ollama",  # required by SDK, ignored by Ollama
        )
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, max_tokens: int, system: str, messages: list) -> _Response:
        response = self._client.chat.completions.create(
            model=_OLLAMA_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}] + messages,
            extra_body={"num_ctx": _OLLAMA_NUM_CTX},
        )
        return _Response(response.choices[0].message.content)


# ── Gemini client ──────────────────────────────────────────────────────────────

_GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiClient:
    """
    Gemini via its OpenAI-compatible endpoint.
    Requires the `openai` package and GEMINI_API_KEY env var.
    Free tier: 15 RPM, 1M token context window — recommended for backfill.
    """

    def __init__(self):
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package required for GeminiClient: pip install openai")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY environment variable.")
        self._client = openai.OpenAI(base_url=_GEMINI_BASE_URL, api_key=api_key)
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, max_tokens: int, system: str, messages: list) -> _Response:
        response = self._client.chat.completions.create(
            model=_GEMINI_MODEL,
            max_tokens=max_tokens,
            temperature=0.0,
            messages=[{"role": "system", "content": system}] + messages,
        )
        return _Response(response.choices[0].message.content)


# ── Factory ────────────────────────────────────────────────────────────────────

def get_client():
    """
    Return an LLM client based on available credentials/config.
    Set USE_OLLAMA=1 to use local Ollama instead of cloud APIs.
    Provider priority: Ollama → Gemini → Groq → Anthropic.
    """
    import logging
    log = logging.getLogger("kvizzing")

    if os.environ.get("USE_OLLAMA"):
        try:
            client = OllamaClient()
            log.info("Using Ollama client (model: %s, ctx: %d)", _OLLAMA_MODEL, _OLLAMA_NUM_CTX)
            return client
        except (ImportError, RuntimeError) as e:
            log.warning("Ollama unavailable (%s) — falling back to cloud APIs.", e)

    for cls in (GeminiClient, GroqClient, AnthropicClient):
        try:
            client = cls()
            log.info("Using %s", cls.__name__)
            return client
        except (ImportError, RuntimeError):
            pass
    log.warning("No LLM client available: Set GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY, or USE_OLLAMA=1.")
    return None

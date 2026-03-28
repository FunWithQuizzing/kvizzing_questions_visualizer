"""
Stage 2 — Extract

Two-phase Q&A extraction:

  Phase 2a — Heuristic pre-filter
    Cheap pattern matching to check whether a day has any quiz activity at all.
    If no candidate messages are found, the LLM call is skipped entirely.

  Phase 2b — LLM extraction
    Send ALL messages for the day in one LLM call and extract every Q&A pair.
    One call per date (not per candidate window) keeps total calls to ~177 for
    a full backfill — well within Groq's 1,000 req/day free tier.

Input:  list of message dicts from Stage 1 (one day's window)
Output: list of raw candidate dicts (not yet Pydantic-validated)
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("kvizzing")


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _parse_json(text: str) -> list:
    """Parse JSON from LLM output, stripping markdown fences if present.
    Falls back to a best-effort repair for unescaped quotes inside strings."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Best-effort repair: replace smart/curly quotes and try again
        repaired = text.replace("\u201c", '\\"').replace("\u201d", '\\"')
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise


def _parse_retry_delay(err_str: str) -> float | None:
    """Extract the suggested retry delay (seconds) from a rate-limit error string."""
    m = re.search(r"retry[_ ]?(?:after|delay|in)[^\d]*(\d+(?:\.\d+)?)", err_str, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# ── Phase 2a — Heuristic pre-filter ──────────────────────────────────────────

_QUESTION_END = re.compile(r"\?$")
_QUESTION_PREFIX = re.compile(
    r"^\s*(Q\.?\s*\d*\.?|Q\d+[.:)]|Flash\s*Q|Question\s*\d*[.:]?)\s*",
    re.IGNORECASE,
)
_SESSION_MARKERS = re.compile(
    r"(###\s*Quiz\s*Start|Round\s*\d|Score\s*\d|Scores?\s*:)",
    re.IGNORECASE,
)


def _is_candidate(msg: dict) -> bool:
    text = msg["text"].strip()
    if _QUESTION_END.search(text):
        return True
    if _QUESTION_PREFIX.match(text):
        return True
    if msg.get("has_media") and len(text) < 30:
        return True
    return False


def _has_enough_replies(
    msg_index: int,
    messages: list[dict],
    window_minutes: int,
    min_replies: int,
) -> bool:
    from zoneinfo import ZoneInfo
    UTC = ZoneInfo("UTC")
    msg = messages[msg_index]
    asker = msg["username"]
    ts = datetime.fromisoformat(msg["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
    deadline = ts + timedelta(minutes=window_minutes)

    repliers: set[str] = set()
    for m in messages[msg_index + 1:]:
        m_ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
        if m_ts > deadline:
            break
        if m["username"] != asker:
            repliers.add(m["username"])
        if len(repliers) >= min_replies:
            return True
    return False


def prefilter(messages: list[dict], config: dict) -> list[int]:
    """
    Return indices of candidate question messages.
    Used as a fast gate — if 0 candidates, skip the LLM call entirely.
    """
    window_minutes: int = config["stage2"]["heuristic_reply_window_minutes"]
    min_replies: int = config["stage2"]["heuristic_min_replies"]

    candidates: list[int] = []
    for i, msg in enumerate(messages):
        if _SESSION_MARKERS.search(msg["text"]):
            candidates.append(i)
            continue
        if _is_candidate(msg) and _has_enough_replies(i, messages, window_minutes, min_replies):
            candidates.append(i)
    return candidates


# ── Phase 2b — LLM extraction (one call per day) ─────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """\
You are an expert at extracting structured Q&A pairs from WhatsApp quiz group chat logs.

You will receive a full day's worth of WhatsApp messages (already parsed, UTC timestamps).
Your task is to extract ALL genuine Q&A pairs present.

A genuine Q&A pair must:
- Have a clearly posed question intended for the group
- Have at least one response from other members (attempts, hints, or a reveal)

For each Q&A pair, output a JSON object with this exact schema:
{
  "question_timestamp": "ISO8601 UTC string",
  "question_text": "full question text",
  "question_asker": "username",
  "topics": ["primary category first, then secondary — from: history, science, literature, technology, sports, geography, entertainment, food_drink, art_culture, business, etymology, general"],
  "has_media": true/false,
  "is_session_question": true/false,
  "session_quizmaster": "username or null",
  "session_theme": "theme string or null",
  "session_question_number": integer or null,
  "answer_text": "the correct answer, or null if never revealed",
  "answer_solver": "username who first got it right, or null",
  "answer_timestamp": "ISO8601 UTC timestamp of winning answer, or null",
  "answer_confirmed": true/false,
  "confirmation_text": "exact confirmation message or null",
  "answer_is_collaborative": true/false,
  "answer_parts": null or [{"label": "X", "text": "answer", "solver": "username or null"}],
  "discussion": [
    {
      "timestamp": "ISO8601 UTC",
      "username": "string",
      "text": "string",
      "role": "attempt|hint|confirmation|chat|answer_reveal",
      "is_correct": true/false/null
    }
  ],
  "scores_after": null or [{"username": "string", "score": integer}],
  "extraction_confidence": "high|medium|low"
}

Rules:
- topics: list all applicable categories with the most relevant (primary) category first; use ["general"] only if none of the specific categories fit
- extraction_confidence "high": asker gave explicit text confirmation (e.g. "Correct!", "Bingo", "Yes!")
- extraction_confidence "medium": strong contextual signal but not explicit confirmation
- extraction_confidence "low": no confirmation found; include anyway
- scores_after: only scores announced AFTER this question's confirmation AND BEFORE the next question starts
- discussion: include all messages from question post to answer confirmation/reveal
- For multi-part questions (X/Y/Z style), populate answer_parts; set answer_is_collaborative if
  different people solved different parts

Output format rules — CRITICAL:
- Return ONLY a valid JSON array. No explanation, no markdown fences, no code blocks.
- If no genuine Q&A pairs are found, return an empty array: []
- All string values MUST be valid JSON strings: escape any double quotes inside strings as \", escape backslashes as \\, escape newlines as \n.
- Do NOT include raw double quotes (") inside string values — always escape them.
- Do NOT truncate or wrap long strings across multiple lines in the JSON output.
"""


def _call_llm(messages: list[dict], config: dict, llm_client) -> list[dict]:
    """
    Send all messages for a day to the LLM in one call.
    Retries on rate limit using the delay suggested by the API.
    """
    model: str = config["stage4"]["llm_model"]
    max_retries: int = config["stage4"]["llm_max_retries"]
    base_delay: float = config["stage4"]["llm_retry_base_delay_seconds"]

    messages_text = "\n".join(
        f"[{m['timestamp']}] {m['username']}: {m['text']}"
        + (" <media>" if m.get("has_media") else "")
        for m in messages
    )
    user_prompt = f"Extract all Q&A pairs from these messages:\n\n{messages_text}"

    for attempt in range(max_retries):
        try:
            response = llm_client.messages.create(
                model=model,
                max_tokens=8192,
                system=_EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return _parse_json(response.content[0].text)
        except json.JSONDecodeError as e:
            log.warning("Stage2 LLM returned invalid JSON (attempt %d): %s", attempt + 1, e)
            return []
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                if attempt < max_retries - 1:
                    delay = _parse_retry_delay(err_str) or base_delay * (2 ** attempt)
                    log.warning("Stage2 rate-limited — retrying in %.1fs (attempt %d/%d)…", delay, attempt + 1, max_retries)
                    time.sleep(delay)
                    continue
            log.error("Stage2 LLM call failed: %s", e, exc_info=True)
            raise
    return []


# ── Phase 2c — Session score detection ───────────────────────────────────────

_SESSION_SCORE_PROMPT = """\
You are analysing a WhatsApp quiz session transcript to find the final score announcement.

The quizmaster sometimes posts a final scores summary at the end of the session.
Extract it if present.

Return a JSON object:
{
  "found": true/false,
  "scores": [{"username": "string", "score": integer}] or null
}

If no score announcement is found, return {"found": false, "scores": null}.
Return ONLY valid JSON, no explanation.
"""


def detect_session_scores(
    session_messages: list[dict],
    config: dict,
    llm_client,
) -> Optional[list[dict]]:
    """
    Phase 2c: scan the full session span for a final score announcement.
    Returns list of {username, score} dicts, or None if not found.
    """
    if not session_messages:
        return None

    model: str = config["stage4"]["llm_model"]
    max_retries: int = config["stage4"]["llm_max_retries"]
    base_delay: float = config["stage4"]["llm_retry_base_delay_seconds"]

    messages_text = "\n".join(
        f"[{m['timestamp']}] {m['username']}: {m['text']}"
        for m in session_messages
    )
    user_prompt = f"Find the final score announcement in this session:\n\n{messages_text}"

    for attempt in range(max_retries):
        try:
            response = llm_client.messages.create(
                model=model,
                max_tokens=512,
                system=_SESSION_SCORE_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            result = _parse_json(response.content[0].text)
            if result.get("found"):
                return result.get("scores")
            return None
        except json.JSONDecodeError as e:
            log.warning("Stage2 session-score LLM returned invalid JSON: %s", e)
            return None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                if attempt < max_retries - 1:
                    delay = _parse_retry_delay(err_str) or base_delay * (2 ** attempt)
                    log.warning("Stage2 session-score rate-limited — retrying in %.1fs…", delay)
                    time.sleep(delay)
                    continue
            log.error("Stage2 session-score LLM call failed: %s", e, exc_info=True)
            raise
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def run(
    messages: list[dict],
    config: dict,
    llm_client=None,
) -> list[dict]:
    """
    Full Stage 2: prefilter gate → one LLM call for the full day → raw candidates.

    If llm_client is None (test mode), returns the prefiltered candidate messages.
    If prefilter finds nothing, skips the LLM call and returns [].
    """
    candidate_indices = prefilter(messages, config)

    if not candidate_indices:
        return []

    if llm_client is None:
        return [messages[i] for i in candidate_indices]

    log.debug("  Stage2: %d heuristic candidates → sending %d messages to LLM",
              len(candidate_indices), len(messages))
    return _call_llm(messages, config, llm_client)

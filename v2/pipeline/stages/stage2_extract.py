"""
Stage 2 — Extract

Two-phase Q&A extraction:

  Phase 2a — Heuristic pre-filter
    Cheap pattern matching to shortlist candidate question messages before
    any LLM calls are made.

  Phase 2b — LLM extraction
    For each candidate, send a ~40-message window to Claude and parse the
    structured response back into raw candidate pairs.

  Phase 2c — Session score detection
    For each detected session, scan the full session span for a final score
    announcement posted after all questions.

Input:  list of message dicts from Stage 1
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


def _parse_json(text: str) -> list:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _parse_retry_delay(err_str: str) -> float | None:
    """Extract the suggested retry delay (seconds) from a rate-limit error string."""
    m = re.search(r"retry[_ ]?(?:after|delay|in)[^\d]*(\d+(?:\.\d+)?)", err_str, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None

# ── Phase 2a — Heuristic pre-filter ───────────────────────────────────────────

# Patterns that strongly suggest a question message
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
    """Return True if this message is a plausible question."""
    text = msg["text"].strip()
    if _QUESTION_END.search(text):
        return True
    if _QUESTION_PREFIX.match(text):
        return True
    if msg.get("has_media") and len(text) < 30:
        # Short caption on a media message — often a quiz image question
        return True
    return False


def _has_enough_replies(
    msg_index: int,
    messages: list[dict],
    window_minutes: int,
    min_replies: int,
) -> bool:
    """
    Return True if the message at msg_index received ≥ min_replies replies
    from distinct users within window_minutes.
    """
    msg = messages[msg_index]
    asker = msg["username"]
    ts = datetime.fromisoformat(msg["timestamp"].rstrip("Z")).replace(
        tzinfo=__import__("zoneinfo").ZoneInfo("UTC")
    )
    deadline = ts + timedelta(minutes=window_minutes)

    repliers: set[str] = set()
    for m in messages[msg_index + 1 :]:
        m_ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(
            tzinfo=__import__("zoneinfo").ZoneInfo("UTC")
        )
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

    A message is included if:
    - It matches a question heuristic AND has ≥ min_replies within the window, OR
    - It contains a session marker (always included regardless of reply count)
    """
    window_minutes: int = config["stage2"]["heuristic_reply_window_minutes"]
    min_replies: int = config["stage2"]["heuristic_min_replies"]

    candidates: list[int] = []
    for i, msg in enumerate(messages):
        if _SESSION_MARKERS.search(msg["text"]):
            candidates.append(i)
            continue
        if _is_candidate(msg):
            if _has_enough_replies(i, messages, window_minutes, min_replies):
                candidates.append(i)

    return candidates


# ── Phase 2b — LLM extraction ─────────────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """\
You are an expert at extracting structured Q&A pairs from WhatsApp quiz group chat logs.

You will receive a window of WhatsApp messages (already parsed, UTC timestamps) centred
on one or more candidate quiz questions. Your task is to extract ALL genuine Q&A pairs
present in the window.

A genuine Q&A pair must:
- Have a clearly posed question intended for the group
- Have at least one response from other members (attempts, hints, or a reveal)

For each Q&A pair, output a JSON object with this exact schema:
{
  "question_timestamp": "ISO8601 UTC string",
  "question_text": "full question text",
  "question_asker": "username",
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
- extraction_confidence "high": asker gave explicit text confirmation (e.g. "Correct!", "Bingo", "Yes!")
- extraction_confidence "medium": strong contextual signal but not explicit confirmation
- extraction_confidence "low": no confirmation found; include anyway
- scores_after: only scores announced AFTER this question's confirmation AND BEFORE the next question starts
- discussion: include all messages from question post to answer confirmation/reveal
- For multi-part questions (X/Y/Z style), populate answer_parts; set answer_is_collaborative if
  different people solved different parts
- If the window contains multiple Q&A pairs, return ALL of them as a JSON array

Return ONLY a valid JSON array of Q&A pair objects. No explanation, no markdown fences.
If no genuine Q&A pairs are found, return an empty array: []
"""


def _build_window(
    candidate_index: int,
    messages: list[dict],
    window_size: int,
) -> list[dict]:
    """Return up to window_size messages centred on the candidate."""
    half = window_size // 2
    start = max(0, candidate_index - half)
    end = min(len(messages), candidate_index + half + 1)
    return messages[start:end]


def _call_llm(
    window: list[dict],
    config: dict,
    llm_client,
) -> list[dict]:
    """
    Call the LLM with the message window and return raw candidate pairs.
    Retries on rate limit with exponential backoff.
    """
    model: str = config["stage4"]["llm_model"]
    max_retries: int = config["stage4"]["llm_max_retries"]
    base_delay: float = config["stage4"]["llm_retry_base_delay_seconds"]

    messages_text = "\n".join(
        f"[{m['timestamp']}] {m['username']}: {m['text']}"
        + (" <media>" if m.get("has_media") else "")
        for m in window
    )
    user_prompt = f"Extract all Q&A pairs from these messages:\n\n{messages_text}"

    for attempt in range(max_retries):
        try:
            response = llm_client.messages.create(
                model=model,
                max_tokens=4096,
                system=_EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text.strip()
            return _parse_json(text)
        except json.JSONDecodeError as e:
            log.warning("Stage2 LLM returned invalid JSON (attempt %d): %s", attempt + 1, e)
            return []
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                if attempt < max_retries - 1:
                    delay = _parse_retry_delay(err_str) or base_delay * (2**attempt)
                    log.warning("Stage2 rate-limited — retrying in %.1fs (attempt %d/%d)…", delay, attempt + 1, max_retries)
                    time.sleep(delay)
                    continue
            # Non-retriable error: log and re-raise so the pipeline fails loudly
            log.error("Stage2 LLM call failed: %s", e, exc_info=True)
            raise
    return []


def _deduplicate_by_timestamp(candidates: list[dict]) -> list[dict]:
    """Remove duplicate candidates with the same question_timestamp."""
    seen: set[str] = set()
    result: list[dict] = []
    for c in candidates:
        ts = c.get("question_timestamp", "")
        if ts not in seen:
            seen.add(ts)
            result.append(c)
    return result


def extract(
    messages: list[dict],
    candidate_indices: list[int],
    config: dict,
    llm_client,
) -> list[dict]:
    """
    Phase 2b: call LLM for each candidate window, collect all raw pairs.
    Overlapping windows may produce duplicates — deduplication happens in Stage 5.
    """
    window_size: int = config["stage2"]["extraction_window_messages"]
    request_delay: float = config["stage2"].get("llm_request_delay_seconds", 2.5)
    all_candidates: list[dict] = []

    for idx in candidate_indices:
        window = _build_window(idx, messages, window_size)
        try:
            pairs = _call_llm(window, config, llm_client)
        except Exception:
            log.warning("Stage2: skipping candidate at index %d due to LLM error.", idx)
            continue
        all_candidates.extend(pairs)
        time.sleep(request_delay)

    return all_candidates


# ── Phase 2c — Session score detection ────────────────────────────────────────

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
                    delay = base_delay * (2**attempt)
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
    Full Stage 2 pipeline: prefilter → LLM extract → return raw candidates.

    If llm_client is None (e.g. in tests), only the prefilter runs and returns
    the candidate messages themselves (not LLM-extracted pairs).
    """
    candidate_indices = prefilter(messages, config)

    if llm_client is None:
        # Test mode: return the candidate messages (no LLM call)
        return [messages[i] for i in candidate_indices]

    return extract(messages, candidate_indices, config, llm_client)

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
You are extracting Q&A pairs from the KVizzing WhatsApp trivia group.

You will receive a DATE and a full day's worth of messages (UTC timestamps). Extract all genuine \
trivia Q&A pairs where question_timestamp starts with that DATE. Messages timestamped the \
following day are lookahead context only — do not extract them as new questions.

---

## INPUT FORMAT

Each line: [ISO8601-UTC-timestamp] username: message text

Multi-line messages are joined with ` ↵ ` (space-arrow-space).

Media markers appear inline: `image omitted`, `GIF omitted`, `video omitted`, `audio omitted`, \
`document omitted`

`<This message was edited>` may appear at the end of messages — ignore it.

---

## WHAT TO EXTRACT

Include: direct trivia questions, session questions (numbered sequences), questions never \
answered or revealed by asker.

Exclude: general chat/memes, questions with zero replies, duplicate posts, questions whose \
timestamp does NOT start with the given DATE.

---

## OUTPUT SCHEMA

Return a JSON array. Each element is a flat object with EXACTLY these fields:

{
  "question_timestamp": "ISO8601Z string — copy verbatim from input",
  "question_text": "full text after cleaning; if has_media, append [image: brief description inferred from discussion, or 'unknown']",
  "question_asker": "username exactly as in chat",
  "topics": ["primary category first — from: history, science, literature, technology, sports, geography, entertainment, food_drink, art_culture, business, etymology, general"],
  "has_media": true if question message had image/GIF/video/audio/document omitted,
  "is_session_question": true if part of a numbered quizmaster session,
  "session_quizmaster": "username or null",
  "session_theme": "announced theme string or null",
  "session_quiz_type": "connect" or null,
  "session_question_number": integer (quizmaster's label) or null,
  "answer_text": "clean enriched answer string, or null if never revealed",
  "answer_solver": "username of first correct solver, or null",
  "answer_timestamp": "timestamp of answer_solver's is_correct=true attempt, or null",
  "answer_confirmed": true/false,
  "confirmation_text": "exact asker confirmation text, or null",
  "answer_is_collaborative": true if different people solved different parts,
  "answer_parts": null or [{"label": "X", "text": "answer", "solver": "username or null"}],
  "discussion": [ {
    "timestamp": "ISO8601Z",
    "username": "string",
    "text": "string",
    "role": "attempt|hint|confirmation|chat|answer_reveal",
    "is_correct": true/false/null
  } ],
  "scores_after": null or [{"username": "string", "score": integer}],
  "extraction_confidence": "high|medium|low"
}

---

## FIELD-BY-FIELD RULES

### topics
List the most relevant category first. Use ["general"] only if no specific category fits.
Valid categories: history, science, literature, technology, sports, geography, entertainment, food_drink, art_culture, business, etymology, general.

### question_text
After cleaning, append [image: brief description inferred from discussion] if has_media=true. \
If nothing can be inferred, write [image: unknown].

### is_session_question / session detection
A session has: (1) quizmaster announcement, (2) explicitly numbered questions, (3) quizmaster \
confirming each answer. Mark is_session_question=true for all questions in such a session.

### session_quiz_type
Set to "connect" if this is a connect quiz — a series of questions sharing a hidden connecting \
theme that participants try to guess (quizmaster may say "guess the connect", "find the \
connection", or reveal the connect at the end). Set to null for regular quizzes.

### answer_text
Enrich the solver's winning attempt with context from the asker's confirmation or reveal. \
Do not copy verbatim if sloppy or hedged. If never answered and never revealed, set null.

### answer_confirmed
true ONLY if the asker sent an explicit text confirmation. Explicit confirms include:
  "correct", "yes", "bingo", "right", "yep", "yess", "yup", "exactly", "indeed", "spot on", \
"perfect", "well done", "✅", "👍", "💯", or any message containing "!"

Do NOT set true if:
- The asker only reacted with an emoji reaction (not a text message)
- The asker elaborated but never said "correct" or equivalent
- Someone other than the asker confirmed
- The asker expressed amazement without confirming ("wow", "amazing", "awesome crack")

### confirmation_text
Exact text of asker's confirmation message. null if answer_confirmed=false.

### answer_timestamp
The timestamp of answer_solver's is_correct=true entry in discussion. NOT the asker's \
confirmation timestamp. null if answer_solver is null.

### answer_parts
Use for any multi-part question (X/Y/Z, identify A and B, etc.), regardless of how many \
people solved it. If answer_parts is present, answer_text must NOT be null.
If answer_parts entries have more than one distinct solver, answer_is_collaborative must be true.

### discussion roles
- attempt: participant's answer try — is_correct must be true or false (NEVER null)
- hint: asker provides a clue (even if it starts with "nope, but...")
- confirmation: asker's direct yes/no with no new information
- chat: banter, reactions, off-topic
- answer_reveal: asker reveals the answer after a confirm or when no one got it
- All non-attempt roles: is_correct must be null (NEVER true or false)

Discussion entries must be in chronological order. No entry may have a timestamp earlier than \
question_timestamp. answer_solver must appear as a username in the discussion array.

### is_correct logic
- true: this attempt directly led to the asker's explicit confirmation
- false: wrong, or close but NOT the confirmed answer
- If asker says "almost", "close", "nearly" → that attempt is false
- If no explicit confirmation but asker revealed same answer → that attempt may be true

### scores_after
null unless quizmaster explicitly lists per-player running totals right after this question. \
Point-value labels ("10 points!", "20 points!") are difficulty labels, NOT scores → null.

### extraction_confidence
- "high": answer_confirmed=true (asker gave explicit text confirmation)
- "medium": no explicit confirmation, but strong contextual signal (reveal, continued without dispute)
- "low": no confirmation, weak or ambiguous signal
NOTE: extraction_confidence="high" if and only if answer_confirmed=true.

### Text cleaning (applies to ALL text fields)
- Replace ` ↵ ` with a space
- Remove <This message was edited> and any invisible characters preceding it
- Do NOT include media marker text ("image omitted" etc.) in any text field

---

## SELF-CHECK BEFORE OUTPUT

1. Does answer_text actually answer question_text?
2. Is answer_solver the FIRST person to give the confirmed-correct answer?
3. Does answer_timestamp match the timestamp of answer_solver's is_correct=true entry?
4. Does every attempt entry have is_correct: true or false (never null)?
5. Does every non-attempt entry have is_correct: null?
6. Is answer_confirmed=true only when the ASKER gave explicit text confirmation?
7. Is extraction_confidence="high" if and only if answer_confirmed=true?
8. Are there any ↵ artifacts, media markers, or edit artifacts in text fields?
9. Are discussion entries in chronological order with no entry before question_timestamp?
10. Does answer_solver appear in the discussion array?
11. If answer_parts is present, is answer_text non-null?
12. If answer_parts has multiple distinct solvers, is answer_is_collaborative=true?

---

Return ONLY a valid JSON array. No markdown fences, no explanation, no preamble.
If no Q&A pairs found for this date, return: []
"""

_FIX_SYSTEM_PROMPT = """\
You are an expert Q&A extractor correcting your own past mistakes.
You were given a task to extract Q&A from WhatsApp, but an automated audit found errors in your JSON.
Please carefully read the provided JSON array and the list of audit errors below it.
Correct the specific fields mentioned in the errors while keeping everything else perfectly intact.
Do NOT delete valid Q&A pairs just to bypass the errors.

Return ONLY a perfectly conforming JSON array.
"""


def _format_messages(messages: list[dict]) -> str:
    return "\n".join(
        f"[{m['timestamp']}] {m['username']}: {m['text']}"
        + (" image omitted" if m.get("has_media") else "")
        for m in messages
    )


def _llm_call_once(messages_text: str, date_str: str, model: str, llm_client) -> str:
    user_prompt = (
        f"DATE: {date_str}\n\n"
        f"Extract all Q&A pairs where question_timestamp starts with {date_str}.\n\n"
        f"=== MESSAGES ===\n{messages_text}"
    )
    response = llm_client.messages.create(
        model=model,
        max_tokens=8192,
        system=_EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _call_llm_chunked(messages: list[dict], date_str: str, model: str, llm_client) -> list[dict]:
    """Split messages into two overlapping halves, extract each, merge by question_timestamp."""
    mid = len(messages) // 2
    overlap = 50  # messages of lookahead context for first chunk
    chunk1 = _format_messages(messages[:mid + overlap])
    chunk2 = _format_messages(messages[mid:])
    log.info("Stage2 chunking into 2 halves (%d / %d messages)…", mid + overlap, len(messages) - mid)
    raw1 = _llm_call_once(chunk1, date_str, model, llm_client)
    time.sleep(1.0)
    raw2 = _llm_call_once(chunk2, date_str, model, llm_client)
    pairs1 = _parse_json(raw1) if raw1.strip() else []
    pairs2 = _parse_json(raw2) if raw2.strip() else []
    seen: dict[str, dict] = {}
    for p in pairs1 + pairs2:
        key = p.get("question_timestamp", "")
        if key not in seen or len(p.get("discussion", [])) > len(seen[key].get("discussion", [])):
            seen[key] = p
    return list(seen.values())


def _call_llm(messages: list[dict], date_str: str, config: dict, llm_client) -> list[dict]:
    """
    Send all messages for a day to the LLM in one call.
    Retries on rate limit; falls back to chunked extraction on persistent JSON errors.
    """
    stage2_cfg = config.get("stage2", {})
    stage4_cfg = config.get("stage4", {})
    model: str = stage2_cfg.get("llm_model") or stage4_cfg.get("llm_model", "")
    max_retries: int = stage2_cfg.get("llm_max_retries") or stage4_cfg.get("llm_max_retries", 3)
    base_delay: float = stage2_cfg.get("llm_retry_base_delay_seconds") or stage4_cfg.get("llm_retry_base_delay_seconds", 2)

    messages_text = _format_messages(messages)

    initial_candidates = None
    for attempt in range(max_retries):
        try:
            raw_text = _llm_call_once(messages_text, date_str, model, llm_client)
            initial_candidates = _parse_json(raw_text)
            break
        except json.JSONDecodeError as e:
            log.warning(
                "Stage2 LLM returned invalid JSON (attempt %d/%d): %s\nRaw response (first 500 chars): %s",
                attempt + 1, max_retries, e, raw_text[:500] if 'raw_text' in dir() else "<no response>",
            )
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning("Stage2 retrying in %.1fs…", delay)
                time.sleep(delay)
                continue
            # All retries exhausted — try chunked extraction if the day is large
            if len(messages) > 100:
                log.warning("Stage2 falling back to chunked extraction (%d messages)…", len(messages))
                try:
                    return _call_llm_chunked(messages, date_str, model, llm_client)
                except Exception as chunk_err:
                    log.error("Stage2 chunked extraction also failed: %s", chunk_err)
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
            
    if not initial_candidates:
        return []

    # ── Self-Healing Audit Loop ──
    from utils.audit_extraction import audit_data
    candidates = initial_candidates
    self_heal_retries = 3
    
    for heal_attempt in range(1, self_heal_retries + 1):
        issues = audit_data(candidates)
        if not issues:
            if heal_attempt > 1:
                log.info("Stage2 self-healing succeeded! Clean data achieved.")
            return candidates
            
        log.warning("Stage2 found %d audit issues on heal attempt %d/%d:", len(issues), heal_attempt, self_heal_retries)
        for issue in issues:
            log.warning("  %s", issue)
            
        if heal_attempt == self_heal_retries:
            break  # Don't spend the last attempt looping, just fall through to raise the error
            
        fix_prompt = (
            "Here is the JSON you previously generated:\n```json\n" + json.dumps(candidates, indent=2, ensure_ascii=False) +
            "\n```\n\nThe automated audit system flagged the following issues:\n" + "\n".join(f"- {i}" for i in issues) +
            "\n\nPlease rewrite and return the ENTIRE JSON array, specifically fixing these issues while preserving all other properties."
        )
        
        try:
            log.info("Stage2 dispatching self-healing LLM call...")
            fix_resp = llm_client.messages.create(
                model=model,
                max_tokens=8192,
                system=_FIX_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": fix_prompt}]
            )
            candidates = _parse_json(fix_resp.content[0].text)
        except Exception as e:
            log.error("Stage2 self-healing LLM call failed or returned unparseable JSON: %s", e)

    # Final enforcement after retries
    final_issues = audit_data(candidates)
    if final_issues:
        error_msg = f"Stage2 failed to resolve {len(final_issues)} audit issues after {self_heal_retries} self-healing attempts:\n" + "\n".join(f"  {i}" for i in final_issues)
        raise RuntimeError(error_msg)
        
    return candidates


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

    stage2_cfg = config.get("stage2", {})
    stage4_cfg = config.get("stage4", {})
    model: str = stage2_cfg.get("llm_model") or stage4_cfg.get("llm_model", "")
    max_retries: int = stage2_cfg.get("llm_max_retries") or stage4_cfg.get("llm_max_retries", 3)
    base_delay: float = stage2_cfg.get("llm_retry_base_delay_seconds") or stage4_cfg.get("llm_retry_base_delay_seconds", 2)

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
    date_str: str = "",
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
    return _call_llm(messages, date_str, config, llm_client)

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

import copy
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
    "is_correct": true/false/null,
    "has_media": true if this message had image/GIF/video/audio/document omitted (hint and answer_reveal only; false for all other roles)
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
  "correct", "yes", "bingo", "right", "yep", "yess", "yesss", "yeas", "yeasss", "yeah", "exactly", \
"indeed", "spot on", "perfect", "well done", "✅", "👍", "💯", "give it to you", \
"giving it to you", "will give", "get it", "full points", "bonus for", "nailed", "closed", \
or any message containing "!"

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

### has_media (discussion entries)
Set has_media=true ONLY on hint and answer_reveal entries whose original message included a media
marker ("image omitted", "GIF omitted", "video omitted", "audio omitted", "document omitted").
Set has_media=false for ALL other roles (attempt, confirmation, chat), even if they had media —
reactions and memes are intentionally excluded. Omit the field or set false when no media present.

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
13. Does has_media=true on every hint/answer_reveal entry that had a media marker? Is has_media=false (or absent) for all other roles?

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
        max_tokens=65536,
        system=_EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _find_quiet_split(messages: list[dict], target_idx: int, lo_bound: int, hi_bound: int, search_range: int = 30) -> int:
    """Find the largest time gap near target_idx to split without cutting a Q&A thread.
    lo_bound/hi_bound prevent this split from crossing into a neighbor's territory."""
    lo = max(lo_bound, target_idx - search_range)
    hi = min(hi_bound - 1, target_idx + search_range)
    best_idx = max(lo_bound, min(hi_bound, target_idx))  # clamp default to valid range
    best_gap = 0.0
    for i in range(lo, hi):
        try:
            t1 = datetime.fromisoformat(messages[i]["timestamp"].rstrip("Z"))
            t2 = datetime.fromisoformat(messages[i + 1]["timestamp"].rstrip("Z"))
            gap = (t2 - t1).total_seconds()
            if gap > best_gap:
                best_gap = gap
                best_idx = i + 1  # split AFTER the gap
        except (ValueError, KeyError):
            continue
    return best_idx


def _merge_extractions(existing: dict, new: dict) -> dict:
    """Merge two extractions of the same question, combining their discussions."""
    # Start with whichever has richer top-level fields
    if existing.get("answer_confirmed") and not new.get("answer_confirmed"):
        base, other = existing, new
    elif new.get("answer_confirmed") and not existing.get("answer_confirmed"):
        base, other = new, existing
    elif len(existing.get("discussion", [])) >= len(new.get("discussion", [])):
        base, other = existing, new
    else:
        base, other = new, existing

    # Merge discussion entries by timestamp+username (dedup)
    merged = copy.deepcopy(base)
    seen_keys: set[str] = set()
    merged_disc: list[dict] = []
    for entry in base.get("discussion", []) + other.get("discussion", []):
        key = f"{entry.get('timestamp')}|{entry.get('username')}"
        if key not in seen_keys:
            seen_keys.add(key)
            merged_disc.append(copy.deepcopy(entry))
    # Sort chronologically
    merged_disc.sort(key=lambda e: e.get("timestamp", ""))
    merged["discussion"] = merged_disc
    return merged


def _call_llm_chunked(messages: list[dict], date_str: str, model: str, llm_client) -> list[dict]:
    """Split messages into overlapping chunks at quiet gaps, extract each, merge by timestamp."""
    overlap = 50  # bidirectional overlap so boundary Q&A threads are seen by both chunks
    target_chunk_size = 600

    # Determine split points
    n_chunks = max(2, (len(messages) + target_chunk_size - 1) // target_chunk_size)
    chunk_size = len(messages) // n_chunks

    # Build split points with bounds so they stay monotonic
    split_points = [0]
    for i in range(1, n_chunks):
        target = chunk_size * i
        # Constrain search: can't go below previous split, can't go above next target
        lo_bound = split_points[-1] + 1
        hi_bound = min(len(messages), chunk_size * (i + 1)) if i < n_chunks - 1 else len(messages)
        if lo_bound >= hi_bound:
            continue  # skip — chunks are too small to split further
        split_points.append(_find_quiet_split(messages, target, lo_bound, hi_bound))
    split_points.append(len(messages))
    n_chunks = len(split_points) - 1  # may have shrunk if chunks were skipped

    log.info("Stage2 chunking into %d parts at quiet gaps (%d messages total)…",
             n_chunks, len(messages))

    seen: dict[str, dict] = {}
    for ci in range(n_chunks):
        # Add overlap in both directions
        start = max(0, split_points[ci] - (overlap if ci > 0 else 0))
        end = min(len(messages), split_points[ci + 1] + (overlap if ci < n_chunks - 1 else 0))
        chunk_text = _format_messages(messages[start:end])
        log.debug("  Chunk %d/%d: messages %d–%d (%d msgs)", ci + 1, n_chunks, start, end - 1, end - start)
        try:
            raw = _llm_call_once(chunk_text, date_str, model, llm_client)
            pairs = _parse_json(raw) if raw.strip() else []
            for p in pairs:
                key = p.get("question_timestamp", "")
                if key in seen:
                    seen[key] = _merge_extractions(seen[key], p)
                else:
                    seen[key] = p
        except Exception as e:
            log.warning("  Chunk %d/%d failed: %s — continuing with remaining chunks", ci + 1, n_chunks, e)
        if ci < n_chunks - 1:
            time.sleep(13)  # Gemini free tier: 5 RPM

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
    tried_chunked = False
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
                tried_chunked = True
                try:
                    initial_candidates = _call_llm_chunked(messages, date_str, model, llm_client)
                    break
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

    if not initial_candidates and not tried_chunked:
        # LLM returned [] — if the day is large, retry with chunked extraction
        # since the model may have struggled with a big input.
        if len(messages) > 100:
            log.warning("Stage2 LLM returned 0 candidates for %d messages — retrying chunked…", len(messages))
            try:
                initial_candidates = _call_llm_chunked(messages, date_str, model, llm_client)
            except Exception as e:
                log.error("Stage2 chunked retry also returned nothing: %s", e)
    if not initial_candidates:
        return []

    # ── Auto-fix common LLM topic mistakes before audit ──
    _TOPIC_ALIASES = {
        "music": "entertainment", "film": "entertainment", "movies": "entertainment",
        "cinema": "entertainment", "tv": "entertainment", "television": "entertainment",
        "gaming": "entertainment", "anime": "entertainment", "comics": "entertainment",
        "food": "food_drink", "drink": "food_drink", "cuisine": "food_drink",
        "cooking": "food_drink",
        "culture": "art_culture", "art": "art_culture", "religion": "art_culture",
        "politics": "history", "military": "history",
        "math": "science", "mathematics": "science", "medicine": "science",
        "biology": "science", "physics": "science", "chemistry": "science",
        "economics": "business", "finance": "business",
        "language": "etymology", "linguistics": "etymology",
        "nature": "geography", "travel": "geography",
    }
    for entry in initial_candidates:
        if "topics" in entry and isinstance(entry["topics"], list):
            entry["topics"] = [_TOPIC_ALIASES.get(t.lower(), t) for t in entry["topics"]]

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
                max_tokens=65536,
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

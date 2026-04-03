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
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))
from schema import TopicCategory

_ALL_TOPICS = {t.value for t in TopicCategory}
_TOPIC_LIST_STR = ", ".join(t.value for t in TopicCategory)

log = logging.getLogger("kvizzing")


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _parse_json(text: str) -> list:
    """Parse JSON from LLM output, stripping markdown fences if present.
    Handles both plain arrays and {extracted, rejected} objects.
    Falls back to a best-effort repair for unescaped quotes inside strings."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        parsed = json.loads(text)
        # Handle new format: {"extracted": [...], "rejected": [...]}
        if isinstance(parsed, dict) and "extracted" in parsed:
            return parsed
        return parsed
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

Exclude:
- General chat, memes, jokes shared for fun (not as a question to be answered)
- Messages that explicitly say they are NOT a question (e.g. "just sharing this", "reminded me of", \
"not a question but", "putting this as a question just to share")
- Questions with zero replies
- Duplicate posts
- Questions whose timestamp does NOT start with the given DATE
- Rhetorical questions, opinions phrased as questions, meta-discussion about the group

---

## OUTPUT SCHEMA

Return a JSON array. Each element is a flat object with EXACTLY these fields:

{
  "question_timestamp": "ISO8601Z string — copy verbatim from input",
  "question_text": "full text after cleaning; if has_media, append [image: brief description inferred from discussion, or 'unknown']",
  "question_asker": "username exactly as in chat",
  "topics": ["primary category first — from: """ + _TOPIC_LIST_STR + """"],
  "has_media": true if question message had image/GIF/video/audio/document omitted,
  "is_session_question": true if part of a numbered quizmaster session,
  "session_quizmaster": "username or null",
  "session_theme": "announced theme string or null",
  "session_quiz_type": "connect" or null,
  "session_announcement": "the quizmaster's introductory message announcing/describing the session, or null",
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
    "role": "attempt|hint|confirmation|chat|answer_reveal|elaboration",
    "is_correct": true/false/null,
    "has_media": true if this message had image/GIF/video/audio/document omitted (hint, answer_reveal, and elaboration only; false for all other roles)
  } ],
  "scores_after": null or [{"username": "string", "score": integer}],
  "extraction_confidence": "high|medium|low"
}

---

## FIELD-BY-FIELD RULES

### topics
List the most relevant category first (up to 3). Use ["general"] ONLY as a last resort when no specific category fits.
Valid categories: """ + _TOPIC_LIST_STR + """.
- Use "meme" for jokes, puns, visual puns, "complete the joke", "caption this", humour-based questions.
- Use "etymology" for language identification, word origins, acronyms, foreign language questions.
- Use "geography" for maps, airports, IATA codes, city/country identification, flags.
- Use "mythology" for myths, fables, legends, epics, religious stories.
- Use "politics" for elections, leaders, geopolitics, diplomacy, governance, sanctions, treaties.
- Prefer a specific topic over "general" — most questions have a clear domain.

### question_text
After cleaning, append [image: brief description inferred from discussion] if has_media=true. \
If nothing can be inferred, write [image: unknown].

### is_session_question / session detection
A session is a series of related questions asked by ONE person (the quizmaster). Sessions can be:
- **Formal**: quizmaster announces a quiz, numbers questions (Q1, Q2…), confirms answers.
- **Informal**: one person asks 4+ questions in a row within a few hours, often with a theme \
(e.g. "badly explained plots", "identify" questions, "guess the song", emoji puzzles, etc.) \
even without explicit numbering or announcements.

Mark is_session_question=true for ALL questions in such a session. Set session_quizmaster to \
the person asking the questions. Set session_theme if a theme is apparent (announced or inferred \
from the pattern). Set session_question_number based on the order within the session.

### session_announcement
The quizmaster's introductory message before/at the start of the session. This is the message \
where they announce the quiz, describe the theme, set rules, or introduce the format. \
Copy the full text (cleaned). Only set on the FIRST question of the session (session_question_number=1). \
Set to null for subsequent questions and non-session questions.

### session_quiz_type
Set to "connect" if this is a connect quiz — a series of questions sharing a hidden connecting \
theme that participants try to guess (quizmaster may say "guess the connect", "find the \
connection", or reveal the connect at the end). Set to null for regular quizzes.

### answer_text
Enrich the solver's winning attempt with context from the asker's confirmation or reveal. \
Do not copy verbatim if sloppy or hedged. If never answered and never revealed, set null.

### answer_confirmed
true ONLY if the asker sent an explicit text confirmation. Explicit confirms include:
  "correct", "correcto", "yes", "bingo", "right", "yep", "yup", "yess", "yesss", "yeas", "yeasss", "yeah", "exactly", \
"indeed", "spot on", "perfect", "well done", "superb", "haan", "ho gaya", "✅", "👍", "💯", \
"give it to you", "giving it to you", "will give", "I'll give", "get it", "full points", \
"bonus for", "nailed", "closed", "exact answer", "answer is", "is the answer", \
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
- elaboration: additional context, trivia, or explanation about the answer/question posted \
AFTER the answer is confirmed or revealed — by the asker OR any participant. Examples: \
"Fun fact: this was also...", "The full story is...", "This is because...", historical context, \
related trivia, corrections, or interesting follow-up information.
- All non-attempt roles: is_correct must be null (NEVER true or false)

### has_media (discussion entries)
Set has_media=true ONLY on hint, answer_reveal, and elaboration entries whose original message \
included a media marker ("image omitted", "GIF omitted", "video omitted", "audio omitted", \
"document omitted").
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
13. Does has_media=true on every hint/answer_reveal/elaboration entry that had a media marker? Is has_media=false (or absent) for all other roles?
14. If is_session_question=true, is session_quizmaster set? Is session_question_number correct?
15. Is session_announcement set ONLY on the first question of each session (session_question_number=1)?
16. Are session fields (session_quizmaster, session_theme, etc.) null for non-session questions?

---

Return a JSON object with two keys:
{
  "extracted": [ ...array of Q&A objects as described above... ],
  "rejected": [
    {
      "timestamp": "ISO8601Z — the message timestamp",
      "username": "who said it",
      "text": "the message text (first 200 chars)",
      "reason": "brief reason why this was NOT extracted (e.g. 'rhetorical question', 'no replies', 'general chat', 'duplicate', 'follow-up to extracted Q')"
    }
  ]
}

The "rejected" array should contain messages that LOOK like trivia questions (end with ?, \
have quiz-like phrasing, or got replies from multiple people) but you chose NOT to extract. \
This helps us audit what was missed. Include 0–20 most plausible rejected candidates. \
Skip obvious non-questions (greetings, reactions, links). \
If no Q&A pairs found, return: {"extracted": [], "rejected": [...]}
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

    # Recompute answer_solver/answer_timestamp from merged discussion
    # so they match the actual first correct attempt after combining chunks.
    if merged.get("answer_solver"):
        first_correct = next(
            (e for e in merged_disc if e.get("is_correct") is True),
            None,
        )
        if first_correct:
            merged["answer_solver"] = first_correct["username"]
            merged["answer_timestamp"] = first_correct["timestamp"]

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
            parsed = _parse_json(raw) if raw.strip() else []
            pairs = _extract_rejected(parsed, date_str) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
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


# Module-level storage for rejected candidates from the LLM
_last_rejected: dict[str, list[dict]] = {}  # date_str → list of rejected candidate dicts


def get_rejected(date_str: str) -> list[dict]:
    """Retrieve rejected candidates from the last LLM call for a date."""
    return _last_rejected.pop(date_str, [])


def _extract_rejected(parsed: object, date_str: str) -> list[dict]:
    """If the LLM returned {extracted, rejected}, split them and store rejected."""
    if isinstance(parsed, dict) and "extracted" in parsed:
        rejected = parsed.get("rejected") or []
        _last_rejected[date_str] = rejected
        return parsed["extracted"]
    # Old format — plain array, no rejected
    return parsed if isinstance(parsed, list) else []


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
            parsed = _parse_json(raw_text)
            initial_candidates = _extract_rejected(parsed, date_str)
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
            if "429" in err_str or "503" in err_str or "rate_limit" in err_str.lower() or "resource_exhausted" in err_str.lower() or "unavailable" in err_str.lower():
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
        "military": "history",
        "math": "science", "mathematics": "science", "medicine": "science",
        "biology": "science", "physics": "science", "chemistry": "science",
        "economics": "business", "finance": "business",
        "language": "etymology", "linguistics": "etymology",
        "nature": "geography", "travel": "geography",
        "memes": "meme", "joke": "meme", "humor": "meme", "humour": "meme",
        "political": "politics", "election": "politics", "government": "politics",
        "parliament": "politics", "democracy": "politics", "geopolitics": "politics",
        "diplomacy": "politics", "geopolitical": "politics",
    }
    for entry in initial_candidates:
        if "topics" in entry and isinstance(entry["topics"], list):
            entry["topics"] = [_TOPIC_ALIASES.get(t.lower(), t) for t in entry["topics"]]

    # ── Auto-fix consistency constraints ──
    _MEDIA_MARKERS_LOWER = {"image omitted", "gif omitted", "video omitted",
                            "audio omitted", "document omitted"}
    _FORMAT_TAGS = {"identify", "anagram", "wordplay", "connect", "clickbait",
                    "real life", "naming", "weird", "pun", "battle",
                    "fill in the blank", "multi-part", "factual"}
    for entry in initial_candidates:
        disc = entry.get("discussion", [])

        # Fix FORMAT_TAG — remove format descriptors from tags
        tags = entry.get("tags") or []
        clean_tags = [t for t in tags if t.lower() not in _FORMAT_TAGS]
        if len(clean_tags) != len(tags):
            entry["tags"] = clean_tags

        # Fix TAG_VARIANT — normalize tag names
        if entry.get("tags"):
            entry["tags"] = ["badly explained" if t.lower() == "badly explained plots" else t
                             for t in entry["tags"]]

        # Fix ARTIFACT — strip ↵ and edit markers from text fields
        for field in ("question_text", "answer_text", "confirmation_text"):
            val = entry.get(field) or ""
            if val:
                cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                if cleaned != val:
                    entry[field] = cleaned if cleaned else None
        for e in disc:
            val = e.get("text") or ""
            if val:
                cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                if cleaned != val:
                    e["text"] = cleaned

        # Fix COLLAB_MISMATCH
        parts = entry.get("answer_parts") or []
        if parts and not entry.get("answer_is_collaborative"):
            solvers = {p["solver"] for p in parts if p.get("solver")}
            if len(solvers) > 1:
                entry["answer_is_collaborative"] = True

        # Fix WRONG_CONFIRMER — non-asker confirmation
        asker = entry.get("question_asker")
        if asker:
            for e in disc:
                if e.get("role") == "confirmation" and e.get("username") != asker:
                    e["role"] = "chat"
                    e["is_correct"] = None

        # Fix HIGH_NOT_CONFIRMED / MEDIUM_BUT_CONFIRMED oscillation
        if entry.get("answer_confirmed"):
            if entry.get("extraction_confidence") != "high":
                entry["extraction_confidence"] = "high"
        else:
            if entry.get("extraction_confidence") == "high":
                entry["extraction_confidence"] = "medium"

        # Fix ORPHAN_SESSION_VAR — clear session fields on non-session questions
        if not entry.get("is_session_question"):
            for f in ("session_quizmaster", "session_theme", "session_quiz_type", "session_question_number", "session_announcement"):
                if entry.get(f):
                    entry[f] = None

        # Fix SOLVER_MISMATCH / TIMESTAMP_MISMATCH from discussion data
        solver = entry.get("answer_solver")
        if solver and not entry.get("answer_is_collaborative") and disc:
            first_correct = next(
                (e for e in disc if e.get("is_correct") is True), None
            )
            if first_correct:
                if first_correct["username"] != solver:
                    entry["answer_solver"] = first_correct["username"]
                if first_correct.get("timestamp") != entry.get("answer_timestamp"):
                    entry["answer_timestamp"] = first_correct["timestamp"]

        # Fix MEDIA_MARKER in confirmation_text
        ct = entry.get("confirmation_text") or ""
        if ct:
            ct_clean = ct
            for marker in _MEDIA_MARKERS_LOWER:
                ct_clean = ct_clean.replace(marker, "").replace(marker.title(), "")
            ct_clean = ct_clean.strip()
            if ct_clean != ct:
                entry["confirmation_text"] = ct_clean if ct_clean else None

        # Fix DISC_MEDIA_ROLE — clear has_media on non-hint/non-reveal entries
        for e in disc:
            if e.get("has_media") and e.get("role") not in ("hint", "answer_reveal", "elaboration"):
                e["has_media"] = False

        # Fix CONFIRM_NO_ROLE — if confirmed but no confirmation role in discussion,
        # try to find the matching chat entry from the asker and reclassify it.
        # If no match found, the confirmation is invalid — set answer_confirmed=false.
        if entry.get("answer_confirmed") and not any(e.get("role") == "confirmation" for e in disc):
            conf_text = (entry.get("confirmation_text") or "").strip()
            asker = entry.get("question_asker")
            matched = False
            for e in disc:
                if (e.get("role") == "chat" and e.get("username") == asker
                        and (not conf_text or e.get("text", "").strip() == conf_text)):
                    e["role"] = "confirmation"
                    e["is_correct"] = None
                    matched = True
                    break
            if not matched:
                entry["answer_confirmed"] = False
                entry["confirmation_text"] = None
                entry["extraction_confidence"] = "medium"

        # Fix CONFIRM_TEXT_FALSE — clear confirmation_text when answer_confirmed=false
        if entry.get("confirmation_text") and not entry.get("answer_confirmed"):
            entry["confirmation_text"] = None

        # Fix DISC_NOT_SORTED — sort discussion chronologically
        if disc:
            entry["discussion"] = sorted(disc, key=lambda e: e.get("timestamp", ""))

        # Fix INVALID_TOPIC — remap invalid topics to "general"
        if entry.get("topics"):
            entry["topics"] = [t if t.lower() in _VALID_TOPICS else "general" for t in entry["topics"]]

    # ── Targeted LLM micro-calls for ambiguous confirmations ──
    from utils.audit_extraction import audit_data
    llm_accepted_labels: set[str] = set()  # HH:MM:SS labels the targeted LLM accepted
    issues = audit_data(initial_candidates)
    implicit_issues = [i for i in issues if i.startswith("CONFIRM_IMPLICIT")]
    if implicit_issues and llm_client:
        # Build lookup: audit uses [HH:MM:SS] labels derived from question_timestamp[11:19]
        entries_by_time: dict[str, dict] = {}
        for entry in initial_candidates:
            ts = entry.get("question_timestamp", "")
            if len(ts) >= 19:
                time_key = ts[11:19]
                # Don't overwrite — if two entries share HH:MM:SS, skip the second
                if time_key not in entries_by_time:
                    entries_by_time[time_key] = entry

        # Build index for finding original messages by nearest timestamp
        msg_timestamps = [m["timestamp"] for m in messages]

        def _find_nearest_msg_idx(target_ts: str) -> int | None:
            """Find the message index closest to target_ts (ISO timestamp)."""
            for idx, mts in enumerate(msg_timestamps):
                if mts == target_ts:
                    return idx
            target_prefix = target_ts[:19]
            for idx, mts in enumerate(msg_timestamps):
                if mts[:19] == target_prefix:
                    return idx
            return None

        resolved = 0
        for ci, issue_str in enumerate(implicit_issues):
            # Parse label from "CONFIRM_IMPLICIT    [HH:MM:SS]: "text""
            label = issue_str.split("]")[0].split("[")[-1]
            entry = entries_by_time.get(label)
            if not entry:
                continue

            conf_text = entry.get("confirmation_text") or ""
            q_text = entry.get("question_text") or ""
            asker = entry.get("question_asker") or ""
            solver = entry.get("answer_solver") or ""
            answer = entry.get("answer_text") or ""

            # Get ~10 messages around the confirmation for context
            conf_disc_entries = [
                e for e in entry.get("discussion", [])
                if e.get("role") == "confirmation"
            ]
            context_lines = ""
            if conf_disc_entries:
                conf_msg_idx = _find_nearest_msg_idx(conf_disc_entries[0].get("timestamp", ""))
                if conf_msg_idx is not None:
                    start = max(0, conf_msg_idx - 5)
                    end = min(len(messages), conf_msg_idx + 6)
                    context_lines = "\n".join(
                        f"[{messages[i]['timestamp']}] {messages[i]['username']}: {messages[i]['text'][:200]}"
                        for i in range(start, end)
                    )

            prompt = (
                f"Question: \"{q_text}\"\n"
                f"Asker: {asker}\n"
                f"Answer given by {solver}: \"{answer}\"\n"
                f"Asker's message: \"{conf_text}\"\n"
            )
            if context_lines:
                prompt += f"\nChat context around the confirmation:\n{context_lines}\n"
            prompt += (
                f"\nIs \"{conf_text}\" an EXPLICIT confirmation by the asker ({asker}) that the answer is correct? "
                f"Explicit means clearly saying yes/correct/right/etc or awarding points. "
                f"Answer reveals (explaining the answer) also count as confirmation. "
                f"Amazement (\"wow\", \"great crack\") without saying correct does NOT count.\n\n"
                f"Reply ONLY with a JSON object: {{\"confirmed\": true/false, \"reason\": \"brief explanation\"}}"
            )

            try:
                resp = llm_client.messages.create(
                    model=model,
                    max_tokens=256,
                    system="You are a precise judge of quiz confirmations. Answer only with JSON.",
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = (resp.content[0].text or "").strip()
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw).strip()
                if not raw:
                    raise ValueError("LLM returned empty response")
                result = json.loads(raw)
                if result.get("confirmed") is True:
                    log.info("  LLM confirmed [%s] \"%s\" — reason: %s",
                             label, conf_text, result.get("reason", ""))
                    llm_accepted_labels.add(label)
                    resolved += 1
                else:
                    log.info("  LLM rejected [%s] \"%s\" — reason: %s",
                             label, conf_text, result.get("reason", ""))
                    entry["answer_confirmed"] = False
                    entry["confirmation_text"] = None
                    entry["extraction_confidence"] = "medium"
                    # Reclassify all confirmation discussion entries — if the LLM
                    # says this isn't a confirmation, no confirmation is valid.
                    for e in entry.get("discussion", []):
                        if e.get("role") == "confirmation":
                            e["role"] = "chat"
                            e["is_correct"] = None
                    resolved += 1
            except Exception as e:
                log.warning("  Targeted confirm check failed for [%s]: %s", label, e)

            # Rate limit between micro-calls
            if ci < len(implicit_issues) - 1:
                time.sleep(13)

        if resolved:
            log.info("Stage2 resolved %d/%d CONFIRM_IMPLICIT issues via targeted LLM calls.",
                     resolved, len(implicit_issues))
            # Re-run confidence consistency after targeted fixes
            for entry in initial_candidates:
                if entry.get("answer_confirmed"):
                    entry["extraction_confidence"] = "high"
                elif entry.get("extraction_confidence") == "high":
                    entry["extraction_confidence"] = "medium"

    # ── Self-Healing Audit Loop (for remaining issues) ──
    def _filter_accepted(raw_issues: list[str]) -> list[str]:
        """Remove CONFIRM_IMPLICIT issues for labels the targeted LLM already accepted."""
        if not llm_accepted_labels:
            return raw_issues
        filtered = []
        for issue in raw_issues:
            if issue.startswith("CONFIRM_IMPLICIT") and "[" in issue:
                issue_label = issue.split("]")[0].split("[")[-1]
                if issue_label in llm_accepted_labels:
                    continue
            filtered.append(issue)
        return filtered

    def _apply_auto_fixes(entries: list[dict]) -> None:
        """Re-apply ALL programmatic fixes after self-healing rewrite."""
        for entry in entries:
            # Topics
            if "topics" in entry and isinstance(entry["topics"], list):
                entry["topics"] = [_TOPIC_ALIASES.get(t.lower(), t) for t in entry["topics"]]
            disc = entry.get("discussion", [])
            # Format tags
            tags = entry.get("tags") or []
            clean_tags = [t for t in tags if t.lower() not in _FORMAT_TAGS]
            if len(clean_tags) != len(tags):
                entry["tags"] = clean_tags
            # Tag variants
            if entry.get("tags"):
                entry["tags"] = ["badly explained" if t.lower() == "badly explained plots" else t
                                 for t in entry["tags"]]
            # Artifacts
            for field in ("question_text", "answer_text", "confirmation_text"):
                val = entry.get(field) or ""
                if val:
                    cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                    if cleaned != val:
                        entry[field] = cleaned if cleaned else None
            for e in disc:
                val = e.get("text") or ""
                if val:
                    cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                    if cleaned != val:
                        e["text"] = cleaned
            # Collab mismatch
            parts = entry.get("answer_parts") or []
            if parts and not entry.get("answer_is_collaborative"):
                solvers = {p["solver"] for p in parts if p.get("solver")}
                if len(solvers) > 1:
                    entry["answer_is_collaborative"] = True
            # Wrong confirmer
            asker = entry.get("question_asker")
            if asker:
                for e in disc:
                    if e.get("role") == "confirmation" and e.get("username") != asker:
                        e["role"] = "chat"
                        e["is_correct"] = None
            # Confidence / confirmed consistency
            if entry.get("answer_confirmed"):
                if entry.get("extraction_confidence") != "high":
                    entry["extraction_confidence"] = "high"
            else:
                if entry.get("extraction_confidence") == "high":
                    entry["extraction_confidence"] = "medium"
            # Orphan session fields
            if not entry.get("is_session_question"):
                for f in ("session_quizmaster", "session_theme", "session_quiz_type", "session_question_number", "session_announcement"):
                    if entry.get(f):
                        entry[f] = None
            # Solver / timestamp from discussion
            solver = entry.get("answer_solver")
            if solver and not entry.get("answer_is_collaborative") and disc:
                first_correct = next(
                    (e for e in disc if e.get("is_correct") is True), None
                )
                if first_correct:
                    if first_correct["username"] != solver:
                        entry["answer_solver"] = first_correct["username"]
                    if first_correct.get("timestamp") != entry.get("answer_timestamp"):
                        entry["answer_timestamp"] = first_correct["timestamp"]
            # Media markers in confirmation_text
            ct = entry.get("confirmation_text") or ""
            if ct:
                ct_clean = ct
                for marker in _MEDIA_MARKERS_LOWER:
                    ct_clean = ct_clean.replace(marker, "").replace(marker.title(), "")
                ct_clean = ct_clean.strip()
                if ct_clean != ct:
                    entry["confirmation_text"] = ct_clean if ct_clean else None
            # has_media on wrong roles
            for e in disc:
                if e.get("has_media") and e.get("role") not in ("hint", "answer_reveal", "elaboration"):
                    e["has_media"] = False
            # CONFIRM_NO_ROLE
            if entry.get("answer_confirmed") and not any(e.get("role") == "confirmation" for e in disc):
                conf_text = (entry.get("confirmation_text") or "").strip()
                asker = entry.get("question_asker")
                matched = False
                for e in disc:
                    if (e.get("role") == "chat" and e.get("username") == asker
                            and (not conf_text or e.get("text", "").strip() == conf_text)):
                        e["role"] = "confirmation"
                        e["is_correct"] = None
                        matched = True
                        break
                if not matched:
                    entry["answer_confirmed"] = False
                    entry["confirmation_text"] = None
                    entry["extraction_confidence"] = "medium"
            # confirmation_text when not confirmed
            if entry.get("confirmation_text") and not entry.get("answer_confirmed"):
                entry["confirmation_text"] = None
            # Sort discussion chronologically
            if disc:
                entry["discussion"] = sorted(disc, key=lambda e: e.get("timestamp", ""))
            # Remap invalid topics to "general"
            if entry.get("topics"):
                entry["topics"] = [t if t.lower() in _VALID_TOPICS else "general" for t in entry["topics"]]

    candidates = initial_candidates
    self_heal_retries = 3

    for heal_attempt in range(1, self_heal_retries + 1):
        issues = _filter_accepted(audit_data(candidates))
        if not issues:
            if heal_attempt > 1:
                log.info("Stage2 self-healing succeeded! Clean data achieved.")
            return candidates

        log.warning("Stage2 found %d audit issues on heal attempt %d/%d:", len(issues), heal_attempt, self_heal_retries)
        for issue in issues:
            log.warning("  %s", issue)

        if heal_attempt == self_heal_retries:
            break

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
            _apply_auto_fixes(candidates)  # re-apply after LLM rewrite
        except Exception as e:
            log.error("Stage2 self-healing LLM call failed or returned unparseable JSON: %s", e)

    # Final enforcement after retries
    final_issues = _filter_accepted(audit_data(candidates))
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
            if "429" in err_str or "503" in err_str or "rate_limit" in err_str.lower() or "resource_exhausted" in err_str.lower() or "unavailable" in err_str.lower():
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

"""
Stage 3 — Structure

Maps raw LLM candidate dicts to KVizzingQuestion Pydantic objects:
  - Assigns stable timestamp-based IDs (YYYY-MM-DD-HHMMSS)
  - Computes derived stats fields
  - Validates against the schema
  - Logs failures to data/errors/

Input:  list of raw candidate dicts from Stage 2
Output: list of validated KVizzingQuestion objects
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter
from datetime import datetime, date as Date
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import ValidationError

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "schema"))
from schema import (
    KVizzingQuestion,
    Question,
    Answer,
    AnswerPart,
    DiscussionEntry,
    DiscussionRole,
    Stats,
    Session,
    Score,
    Source,
    Difficulty,
    ExtractionConfidence,
    QuestionType,
)

UTC = ZoneInfo("UTC")

# ── ID generation ──────────────────────────────────────────────────────────────

def _make_id(timestamp_utc_str: str, collision_counter: Counter) -> str:
    """
    Generate a stable timestamp-based ID: YYYY-MM-DD-HHMMSS.
    If two questions share the same second, append a digit suffix: YYYYMMDDHHMMSS2.
    """
    dt = datetime.fromisoformat(timestamp_utc_str.rstrip("Z")).replace(tzinfo=UTC)
    base = dt.strftime("%Y-%m-%d-%H%M%S")
    collision_counter[base] += 1
    count = collision_counter[base]
    if count == 1:
        return base
    return f"{base}{count}"


# ── Stats computation ──────────────────────────────────────────────────────────

def _compute_stats(discussion: list[dict], config: dict) -> dict:
    """Compute Stats fields from the discussion list."""
    easy_max: int = config["stage3"]["difficulty"]["easy_max_wrong_attempts"]
    medium_max: int = config["stage3"]["difficulty"]["medium_max_wrong_attempts"]

    wrong_attempts = sum(
        1 for e in discussion
        if e.get("role") == "attempt" and e.get("is_correct") is False
    )
    hints_given = sum(1 for e in discussion if e.get("role") == "hint")

    # Time to answer: delta from question ts to winning answer ts
    time_to_answer: Optional[int] = None
    correct_entries = [
        e for e in discussion
        if e.get("role") == "attempt" and e.get("is_correct") is True
    ]
    # (question timestamp passed separately by caller)

    participants = {
        e.get("username", "") for e in discussion if e.get("role") == "attempt" and e.get("username")
    }
    unique_participants = len(participants) if participants else None

    # Heuristic difficulty
    if wrong_attempts <= easy_max:
        difficulty = Difficulty.easy
    elif wrong_attempts <= medium_max:
        difficulty = Difficulty.medium
    else:
        difficulty = Difficulty.hard

    return {
        "wrong_attempts": wrong_attempts,
        "hints_given": hints_given,
        "time_to_answer_seconds": time_to_answer,  # computed by caller
        "unique_participants": unique_participants,
        "difficulty": difficulty,
    }


def _compute_time_to_answer(
    question_ts: str, answer_ts: Optional[str]
) -> Optional[int]:
    if not answer_ts:
        return None
    q = datetime.fromisoformat(question_ts.rstrip("Z")).replace(tzinfo=UTC)
    a = datetime.fromisoformat(answer_ts.rstrip("Z")).replace(tzinfo=UTC)
    delta = int((a - q).total_seconds())
    return max(0, delta)


# ── Mapping raw → Pydantic ─────────────────────────────────────────────────────

def _map_discussion(entries: list[dict]) -> list[DiscussionEntry]:
    result = []
    for e in entries:
        try:
            result.append(DiscussionEntry(
                timestamp=datetime.fromisoformat(e["timestamp"].rstrip("Z")).replace(tzinfo=UTC),
                username=e["username"],
                text=e["text"],
                role=DiscussionRole(e["role"]),
                is_correct=e.get("is_correct"),
                media=None,
            ))
        except (KeyError, ValueError):
            continue
    return result


def _map_answer_parts(parts: Optional[list[dict]]) -> Optional[list[AnswerPart]]:
    if not parts:
        return None
    return [
        AnswerPart(
            label=p["label"],
            text=p["text"],
            solver=p.get("solver"),
        )
        for p in parts
    ]


def _map_scores_after(scores: Optional[list[dict]]) -> Optional[list[Score]]:
    if not scores:
        return None
    return [Score(username=s["username"], score=s["score"]) for s in scores]


def _infer_question_type(text: str) -> QuestionType:
    text_lower = text.lower()
    if re.search(r"\b(x|y|z)\b.*\band\b", text_lower):
        return QuestionType.multi_part
    if re.search(r"\bconnect\b|\bcommon (link|thread|connection)\b", text_lower):
        return QuestionType.connect
    if re.search(r"\bidentify\b|\bname the\b|\bwho is\b|\bwhat is this\b", text_lower):
        return QuestionType.identify
    if re.search(r"\b___+\b|_____|\[blank\]|fill in", text_lower):
        return QuestionType.fill_in_blank
    if "?" in text:
        return QuestionType.factual
    return QuestionType.unknown


import re


def structure(
    raw: dict,
    config: dict,
    collision_counter: Counter,
    source_file: str = "_chat.txt",
    pair_index: int = 1,
) -> Optional[KVizzingQuestion]:
    """
    Map a single raw candidate dict to a KVizzingQuestion.
    Returns None on validation failure.
    """
    try:
        q_ts = raw["question_timestamp"]
        q_date = datetime.fromisoformat(q_ts.rstrip("Z")).date()

        discussion_raw = raw.get("discussion", [])
        discussion = _map_discussion(discussion_raw)

        stats_raw = _compute_stats(discussion_raw, config)
        stats_raw["time_to_answer_seconds"] = _compute_time_to_answer(
            q_ts, raw.get("answer_timestamp")
        )
        # Unanswered questions: difficulty is None (Stage 4 LLM will assess)
        if raw.get("answer_text") is None:
            stats_raw["difficulty"] = None

        q_type = _infer_question_type(raw.get("question_text", ""))
        if raw.get("answer_parts"):
            q_type = QuestionType.multi_part

        question = Question(
            timestamp=datetime.fromisoformat(q_ts.rstrip("Z")).replace(tzinfo=UTC),
            text=raw["question_text"],
            asker=raw["question_asker"],
            type=q_type,
            has_media=bool(raw.get("has_media", False)),
            media=None,
            topic=None,
            tags=[],
        )

        answer = Answer(
            text=raw.get("answer_text"),
            solver=raw.get("answer_solver"),
            timestamp=(
                datetime.fromisoformat(raw["answer_timestamp"].rstrip("Z")).replace(tzinfo=UTC)
                if raw.get("answer_timestamp") else None
            ),
            confirmed=bool(raw.get("answer_confirmed", False)),
            confirmation_text=raw.get("confirmation_text"),
            is_collaborative=bool(raw.get("answer_is_collaborative", False)),
            parts=_map_answer_parts(raw.get("answer_parts")),
        )

        stats = Stats(
            wrong_attempts=stats_raw["wrong_attempts"],
            hints_given=stats_raw["hints_given"],
            time_to_answer_seconds=stats_raw["time_to_answer_seconds"],
            unique_participants=stats_raw["unique_participants"],
            difficulty=stats_raw["difficulty"],
        )

        session: Optional[Session] = None
        if raw.get("is_session_question") and raw.get("session_quizmaster"):
            session_date = q_date.strftime("%Y-%m-%d")
            qm_slug = raw["session_quizmaster"].lower().split()[0]
            session = Session(
                id=f"{session_date}-{qm_slug}",
                quizmaster=raw["session_quizmaster"],
                question_number=raw.get("session_question_number") or 1,
                theme=raw.get("session_theme"),
            )

        source = Source(file=source_file, pair_index=pair_index)
        question_id = _make_id(q_ts, collision_counter)

        return KVizzingQuestion(
            id=question_id,
            date=q_date,
            question=question,
            answer=answer,
            discussion=discussion,
            stats=stats,
            extraction_confidence=ExtractionConfidence(
                raw.get("extraction_confidence", "medium")
            ),
            source=source,
            session=session,
            scores_after=_map_scores_after(raw.get("scores_after")),
            reactions=None,
            highlights=None,
        )
    except (KeyError, ValueError, ValidationError):
        return None


# ── Error logging ──────────────────────────────────────────────────────────────

def _log_error(candidate: dict, error: str, errors_dir: pathlib.Path) -> None:
    errors_dir.mkdir(parents=True, exist_ok=True)
    ts = candidate.get("question_timestamp", "unknown")
    date_part = ts[:10] if len(ts) >= 10 else "unknown"
    error_file = errors_dir / f"{date_part}_errors.json"

    existing = []
    if error_file.exists():
        try:
            existing = json.loads(error_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    existing.append({"candidate": candidate, "error": error})
    error_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False, default=str))


# ── Public entry point ────────────────────────────────────────────────────────

def run(
    candidates: list[dict],
    config: dict,
    errors_dir: Optional[pathlib.Path] = None,
    source_file: str = "_chat.txt",
) -> list[KVizzingQuestion]:
    """
    Validate and structure all raw candidates into KVizzingQuestion objects.
    Invalid candidates are logged to errors_dir (if provided) and skipped.
    """
    collision_counter: Counter = Counter()
    results: list[KVizzingQuestion] = []

    for i, candidate in enumerate(candidates):
        try:
            obj = structure(candidate, config, collision_counter, source_file, pair_index=i + 1)
            if obj is None:
                raise ValueError("structure() returned None")
            results.append(obj)
        except Exception as e:
            if errors_dir:
                _log_error(candidate, str(e), errors_dir)

    return results

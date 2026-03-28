"""
Stage 6 — Export

Reads questions.db and writes static JSON files for the visualizer:

  questions.json   — full archive sorted by question.timestamp
  sessions.json    — session index with aggregate metadata + final scores
  stats.json       — pre-aggregated group stats (topics, difficulty, activity)
  tags.json        — tag → [question_id, ...] index for instant filtering
  members.json     — config/members.json merged with computed per-member stats

  pipeline_state.json → last_exported_date updated

Input:  sqlite3 connection to questions.db
Output: JSON files written to output_dir
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from collections import defaultdict
from datetime import date as Date
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_json(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


def _load_payloads(conn: sqlite3.Connection) -> list[dict]:
    """Load all question payloads from the DB, sorted by question timestamp."""
    rows = conn.execute(
        "SELECT payload FROM questions ORDER BY json_extract(payload, '$.question.timestamp')"
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def _load_scores_after(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """
    Return per-question scores keyed by question_id.
    Only includes rows where after_question_id IS NOT NULL.
    """
    rows = conn.execute(
        "SELECT after_question_id, username, score FROM session_scores "
        "WHERE after_question_id IS NOT NULL"
    ).fetchall()
    result: dict[str, list[dict]] = defaultdict(list)
    for qid, username, score in rows:
        result[qid].append({"username": username, "score": score})
    return dict(result)


def _load_final_scores(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """
    Return final session scores keyed by session_id.
    Only includes rows where after_question_id IS NULL.
    """
    rows = conn.execute(
        "SELECT session_id, username, score FROM session_scores "
        "WHERE after_question_id IS NULL"
    ).fetchall()
    result: dict[str, list[dict]] = defaultdict(list)
    for session_id, username, score in rows:
        result[session_id].append({"username": username, "score": score})
    return dict(result)


# ── questions.json ────────────────────────────────────────────────────────────

def build_questions(conn: sqlite3.Connection) -> list[dict]:
    """
    Load all questions from DB, inject per-question scores_after from
    session_scores table, return sorted by question.timestamp.
    """
    payloads = _load_payloads(conn)
    scores_by_qid = _load_scores_after(conn)

    # Fix duplicate question numbers within a session — the LLM often returns
    # null which stage3 coerces to 1, giving every question number=1.
    # Only reassign sequentially (by timestamp) when duplicates are detected;
    # sessions with already-unique numbers keep their LLM-extracted values.
    by_session: dict[str, list[dict]] = defaultdict(list)
    for q in payloads:
        if q.get("session"):
            by_session[q["session"]["id"]].append(q)

    for session_qs in by_session.values():
        nums = [q["session"]["question_number"] for q in session_qs]
        if len(nums) != len(set(nums)):  # duplicates — reassign sequentially
            session_qs.sort(key=lambda q: (q.get("question") or {}).get("timestamp") or q.get("date") or "")
            for i, q in enumerate(session_qs, start=1):
                q["session"]["question_number"] = i

    for q in payloads:
        qid = q["id"]
        session = q.get("session")
        if session:
            q["scores_after"] = scores_by_qid.get(qid) or None
        else:
            q["scores_after"] = None

    return payloads


# ── sessions.json ─────────────────────────────────────────────────────────────

def build_sessions(conn: sqlite3.Connection) -> list[dict]:
    """
    Build a session index with aggregate metadata and final scores.
    One entry per unique session_id, sorted by date.
    """
    rows = conn.execute(
        "SELECT session_id, payload FROM questions WHERE session_id IS NOT NULL"
    ).fetchall()

    if not rows:
        return []

    # Group payloads by session_id
    by_session: dict[str, list[dict]] = defaultdict(list)
    for session_id, payload_str in rows:
        by_session[session_id].append(json.loads(payload_str))

    final_scores = _load_final_scores(conn)

    sessions = []
    for session_id, questions in by_session.items():
        # Get metadata from any question (all share the same session info)
        s = questions[0].get("session", {})

        # Aggregate stats
        times = [
            q["stats"]["time_to_answer_seconds"]
            for q in questions
            if q["stats"].get("time_to_answer_seconds") is not None
        ]
        wrong = [q["stats"]["wrong_attempts"] for q in questions]
        participants: set[str] = set()
        for q in questions:
            for entry in q.get("discussion", []):
                if entry.get("role") == "attempt" and entry.get("username"):
                    participants.add(entry["username"])

        sessions.append({
            "id": session_id,
            "quizmaster": s.get("quizmaster"),
            "theme": s.get("theme"),
            "date": questions[0].get("date"),
            "question_count": len(questions),
            "avg_time_to_answer_seconds": (
                round(sum(times) / len(times), 1) if times else None
            ),
            "avg_wrong_attempts": (
                round(sum(wrong) / len(wrong), 2) if wrong else None
            ),
            "participant_count": len(participants) if participants else None,
            "scores": final_scores.get(session_id) or None,
        })

    sessions.sort(key=lambda s: s["date"] or "")
    return sessions


# ── stats.json ────────────────────────────────────────────────────────────────

def build_stats(questions: list[dict]) -> dict:
    """Pre-aggregate group stats from question list."""
    topic_dist: dict[str, int] = defaultdict(int)
    difficulty_dist: dict[str, int] = defaultdict(int)
    activity: dict[str, int] = defaultdict(int)  # date → question count
    session_ids: set[str] = set()

    for q in questions:
        topic = (q.get("question") or {}).get("topic")
        if topic:
            topic_dist[topic] += 1

        difficulty = (q.get("stats") or {}).get("difficulty")
        if difficulty:
            difficulty_dist[difficulty] += 1

        date = q.get("date", "")
        if date:
            activity[date] += 1

        session = q.get("session")
        if session and session.get("id"):
            session_ids.add(session["id"])

    return {
        "total_questions": len(questions),
        "total_sessions": len(session_ids),
        "topic_distribution": dict(topic_dist),
        "difficulty_distribution": dict(difficulty_dist),
        "session_activity": [
            {"date": d, "question_count": c}
            for d, c in sorted(activity.items())
        ],
    }


# ── tags.json ─────────────────────────────────────────────────────────────────

def build_tags(questions: list[dict]) -> dict[str, list[str]]:
    """Build tag → [question_id, ...] index."""
    index: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        qid = q["id"]
        tags = (q.get("question") or {}).get("tags") or []
        for tag in tags:
            index[tag].append(qid)
    return dict(index)


# ── members.json ──────────────────────────────────────────────────────────────

def build_members(
    questions: list[dict],
    config_members: list[dict],
) -> list[dict]:
    """
    Merge config/members.json (display_name, color, avatar_url) with
    per-member stats computed from questions.

    Members in the data but absent from config get the raw username as
    display_name; color is null (derived client-side via hash fallback).
    """
    # Index config by username
    config_by_username: dict[str, dict] = {m["username"]: m for m in config_members}

    # Compute stats
    asked: dict[str, int] = defaultdict(int)
    solved: dict[str, int] = defaultdict(int)
    attempts: dict[str, int] = defaultdict(int)
    sessions_hosted: dict[str, set] = defaultdict(set)
    solve_times: dict[str, list[int]] = defaultdict(list)

    for q in questions:
        asker = (q.get("question") or {}).get("asker")
        if asker:
            asked[asker] += 1

        solver = (q.get("answer") or {}).get("solver")
        time_s = (q.get("stats") or {}).get("time_to_answer_seconds")
        if solver:
            solved[solver] += 1
            if time_s is not None:
                solve_times[solver].append(time_s)

        session = q.get("session")
        if session:
            qm = session.get("quizmaster")
            sid = session.get("id")
            if qm and sid:
                sessions_hosted[qm].add(sid)

        for entry in q.get("discussion", []):
            if entry.get("role") == "attempt" and entry.get("username"):
                attempts[entry["username"]] += 1

    # Collect all usernames seen in the data
    all_usernames: set[str] = set()
    all_usernames.update(asked.keys())
    all_usernames.update(solved.keys())
    all_usernames.update(attempts.keys())
    all_usernames.update(sessions_hosted.keys())

    members = []
    for username in sorted(all_usernames):
        cfg = config_by_username.get(username, {})
        times = solve_times.get(username, [])
        members.append({
            "username": username,
            "display_name": cfg.get("display_name", username),
            "color": cfg.get("color"),
            "avatar_url": cfg.get("avatar_url"),
            "questions_asked": asked.get(username, 0),
            "questions_solved": solved.get(username, 0),
            "total_attempts": attempts.get(username, 0),
            "sessions_hosted": len(sessions_hosted.get(username, set())),
            "avg_solve_time_seconds": (
                round(sum(times) / len(times), 1) if times else None
            ),
        })

    return members


# ── Pipeline state ────────────────────────────────────────────────────────────

def _update_state(state_path: pathlib.Path, exported_date: str) -> None:
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    state["last_exported_date"] = exported_date
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ── Public entry point ────────────────────────────────────────────────────────

def run(
    conn: sqlite3.Connection,
    output_dir: pathlib.Path,
    members_config_path: Optional[pathlib.Path] = None,
    state_path: Optional[pathlib.Path] = None,
) -> dict[str, int]:
    """
    Export all JSON files to output_dir.
    Returns a dict of {filename: item_count} for logging.
    """
    output_dir = pathlib.Path(output_dir)

    # Load questions once — reused by stats, tags, members
    questions = build_questions(conn)

    # Load members config
    config_members: list[dict] = []
    if members_config_path and pathlib.Path(members_config_path).exists():
        config_members = json.loads(
            pathlib.Path(members_config_path).read_text(encoding="utf-8")
        )

    sessions = build_sessions(conn)
    stats = build_stats(questions)
    tags = build_tags(questions)
    members = build_members(questions, config_members)

    _write_json(output_dir / "questions.json", questions)
    _write_json(output_dir / "sessions.json", sessions)
    _write_json(output_dir / "stats.json", stats)
    _write_json(output_dir / "tags.json", tags)
    _write_json(output_dir / "members.json", members)

    if state_path and questions:
        dates = [q["date"] for q in questions if q.get("date")]
        if dates:
            _update_state(pathlib.Path(state_path), max(dates))

    return {
        "questions": len(questions),
        "sessions": len(sessions),
        "tags": len(tags),
        "members": len(members),
    }

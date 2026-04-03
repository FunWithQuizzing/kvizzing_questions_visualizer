"""
Stage 5 — Store

Upserts KVizzingQuestion objects into SQLite (questions.db):
  - Creates the schema on first run (questions table, FTS5 virtual table,
    session_scores table)
  - INSERT OR REPLACE on id — safe for incremental and re-runs
  - Each date's batch is wrapped in a single transaction
  - Per-question session scores upserted into session_scores table
  - Updates data/pipeline_state.json → last_stored_date

Input:  list of KVizzingQuestion objects from Stage 4
Output: questions.db updated in place; pipeline_state.json updated
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from collections import defaultdict
from datetime import date as Date
from typing import Optional

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "schema"))
from schema import KVizzingQuestion


# ── Schema DDL ────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS questions (
    id                    TEXT PRIMARY KEY,
    date                  TEXT NOT NULL,
    asker                 TEXT NOT NULL,
    solver                TEXT,
    session_id            TEXT,
    topic                 TEXT,
    difficulty            TEXT,
    extraction_confidence TEXT NOT NULL,
    has_media             INTEGER NOT NULL DEFAULT 0,
    has_reactions         INTEGER NOT NULL DEFAULT 0,
    payload               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_date       ON questions(date);
CREATE INDEX IF NOT EXISTS idx_questions_asker      ON questions(asker);
CREATE INDEX IF NOT EXISTS idx_questions_solver     ON questions(solver);
CREATE INDEX IF NOT EXISTS idx_questions_session    ON questions(session_id);
CREATE INDEX IF NOT EXISTS idx_questions_topic      ON questions(topic);
CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_has_media  ON questions(has_media);

CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts USING fts5(
    id UNINDEXED,
    question_text,
    answer_text,
    tags
);

CREATE TABLE IF NOT EXISTS session_scores (
    session_id        TEXT NOT NULL,
    after_question_id TEXT,
    username          TEXT NOT NULL,
    score             INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_session_scores
    ON session_scores(session_id, COALESCE(after_question_id, ''), username);
"""


# ── DB initialisation ─────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables, indices, and triggers if they don't exist."""
    conn.executescript(_DDL)
    conn.commit()


# ── Serialisation ─────────────────────────────────────────────────────────────

def _to_row(q: KVizzingQuestion) -> tuple:
    """Convert a KVizzingQuestion to a questions-table row tuple."""
    payload = q.model_dump_json()
    return (
        q.id,
        str(q.date),
        q.question.asker,
        q.answer.solver,
        q.session.id if q.session else None,
        q.question.topics[0].value if q.question.topics else None,
        q.stats.difficulty.value if q.stats.difficulty else None,
        q.extraction_confidence.value,
        1 if q.question.has_media else 0,
        1 if q.reactions else 0,
        payload,
    )


# ── Upsert ────────────────────────────────────────────────────────────────────

_INSERT_SQL = """
INSERT OR REPLACE INTO questions
    (id, date, asker, solver, session_id, topic, difficulty,
     extraction_confidence, has_media, has_reactions, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SCORE_UPSERT_SQL = """
INSERT OR REPLACE INTO session_scores (session_id, after_question_id, username, score)
VALUES (?, ?, ?, ?)
"""


_FTS_INSERT_SQL = (
    "INSERT INTO questions_fts(rowid, id, question_text, answer_text, tags) "
    "VALUES (?, ?, ?, ?, ?)"
)


def _upsert_fts(q: KVizzingQuestion, conn: sqlite3.Connection) -> None:
    """
    Sync the FTS5 index for one question.
    If the question already exists, delete its stale FTS entry by rowid before
    re-inserting. INSERT OR REPLACE assigns a new rowid to the replaced row, so
    the old FTS entry must be removed explicitly.
    """
    existing = conn.execute(
        "SELECT rowid FROM questions WHERE id = ?", (q.id,)
    ).fetchone()

    if existing:
        conn.execute("DELETE FROM questions_fts WHERE rowid = ?", (existing[0],))

    # INSERT OR REPLACE assigns a new rowid — fetch it after the write.
    conn.execute(_INSERT_SQL, _to_row(q))
    new_rowid = conn.execute(
        "SELECT rowid FROM questions WHERE id = ?", (q.id,)
    ).fetchone()[0]
    conn.execute(_FTS_INSERT_SQL, (
        new_rowid, q.id, q.question.text, q.answer.text,
        json.dumps(q.question.tags),
    ))


def upsert(questions: list[KVizzingQuestion], conn: sqlite3.Connection) -> int:
    """
    Upsert a list of questions, grouped by date — each date in one transaction.
    Also upserts per-question session scores from question.scores_after.
    Returns total number of questions upserted.
    """
    by_date: dict[str, list[KVizzingQuestion]] = defaultdict(list)
    for q in questions:
        by_date[str(q.date)].append(q)

    total = 0
    for _date, batch in sorted(by_date.items()):
        with conn:
            for q in batch:
                _upsert_fts(q, conn)
                if q.session and q.scores_after:
                    score_rows = [
                        (q.session.id, q.id, s.username, s.score)
                        for s in q.scores_after
                    ]
                    conn.executemany(_SCORE_UPSERT_SQL, score_rows)
        total += len(batch)

    return total


def upsert_session_final_scores(
    session_id: str,
    scores: list[dict],
    conn: sqlite3.Connection,
) -> None:
    """
    Upsert final session scores (after_question_id = null).
    scores is a list of {username: str, score: int} dicts.
    """
    rows = [(session_id, None, s["username"], s["score"]) for s in scores]
    with conn:
        conn.executemany(_SCORE_UPSERT_SQL, rows)


# ── Load helpers ─────────────────────────────────────────────────────────────

def load_all(conn: sqlite3.Connection) -> list[KVizzingQuestion]:
    """Load every question from the DB as KVizzingQuestion objects."""
    import logging
    log = logging.getLogger("kvizzing")
    rows = conn.execute("SELECT payload FROM questions").fetchall()
    questions = []
    for (payload,) in rows:
        try:
            questions.append(KVizzingQuestion.model_validate_json(payload))
        except Exception as e:
            log.warning("Skipping malformed row: %s", e)
    return questions


# ── Pipeline state ────────────────────────────────────────────────────────────

def _load_state(state_path: pathlib.Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_stored_date": None, "last_exported_date": None, "total_questions": 0}


def _save_state(state_path: pathlib.Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def update_state(
    questions: list[KVizzingQuestion],
    conn: sqlite3.Connection,
    state_path: pathlib.Path,
) -> None:
    """Update pipeline_state.json after a successful store run."""
    if not questions:
        return

    state = _load_state(state_path)

    # last_stored_date = max date among stored questions
    max_date = str(max(q.date for q in questions))
    current = state.get("last_stored_date")
    if current is None or max_date > current:
        state["last_stored_date"] = max_date

    # total_questions = live count from DB
    row = conn.execute("SELECT COUNT(*) FROM questions").fetchone()
    state["total_questions"] = row[0] if row else 0

    _save_state(state_path, state)


# ── Public entry point ────────────────────────────────────────────────────────

def run(
    questions: list[KVizzingQuestion],
    conn: sqlite3.Connection,
    state_path: Optional[pathlib.Path] = None,
) -> int:
    """
    Full Stage 5: init schema, upsert questions, update pipeline state.
    Returns number of questions upserted.
    """
    init_db(conn)
    count = upsert(questions, conn)

    if state_path is not None and questions:
        update_state(questions, conn, state_path)

    return count

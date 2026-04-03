"""Tests for Stage 5 — Store."""

import json
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))

from stages.stage5_store import (
    init_db,
    upsert,
    upsert_session_final_scores,
    update_state,
    run,
    _to_row,
)
from stages.stage3_structure import structure
from schema import KVizzingQuestion, TopicCategory, Difficulty

BASE_CONFIG = {
    "stage3": {
        "difficulty": {
            "easy_max_wrong_attempts": 0,
            "medium_max_wrong_attempts": 3,
        }
    }
}

_BASE_CANDIDATE = {
    "question_timestamp": "2025-09-23T19:25:40Z",
    "question_text": "What economic principle was established by the repeal of the Corn Laws?",
    "question_asker": "Pavan",
    "has_media": False,
    "is_session_question": False,
    "session_quizmaster": None,
    "session_theme": None,
    "session_question_number": None,
    "answer_text": "Free trade",
    "answer_solver": "Aditi",
    "answer_timestamp": "2025-09-23T19:27:10Z",
    "answer_confirmed": True,
    "confirmation_text": "Bingo!",
    "answer_is_collaborative": False,
    "answer_parts": None,
    "discussion": [
        {"timestamp": "2025-09-23T19:27:10Z", "username": "Aditi", "text": "Free trade!", "role": "attempt", "is_correct": True},
    ],
    "scores_after": None,
    "extraction_confidence": "high",
}


def _make_question(timestamp_offset: int = 0, **overrides) -> KVizzingQuestion:
    import copy
    from datetime import datetime, timezone, timedelta
    c = copy.deepcopy(_BASE_CANDIDATE)
    c.update(overrides)
    if timestamp_offset:
        base = datetime(2025, 9, 23, 19, 25, 40, tzinfo=timezone.utc)
        new_ts = (base + timedelta(seconds=timestamp_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["question_timestamp"] = new_ts
        c["answer_timestamp"] = (base + timedelta(seconds=timestamp_offset + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["discussion"][0]["timestamp"] = c["answer_timestamp"]
    return structure(c, BASE_CONFIG, Counter())


def _make_session_question(timestamp_offset: int = 0, scores_after=None) -> KVizzingQuestion:
    import copy
    from datetime import datetime, timezone, timedelta
    c = copy.deepcopy(_BASE_CANDIDATE)
    c["is_session_question"] = True
    c["session_quizmaster"] = "pratik.s.chandarana"
    c["session_theme"] = "Movies"
    c["session_question_number"] = 1
    if scores_after is not None:
        c["scores_after"] = scores_after
    if timestamp_offset:
        base = datetime(2025, 9, 23, 19, 25, 40, tzinfo=timezone.utc)
        new_ts = (base + timedelta(seconds=timestamp_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["question_timestamp"] = new_ts
        c["answer_timestamp"] = (base + timedelta(seconds=timestamp_offset + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["discussion"][0]["timestamp"] = c["answer_timestamp"]
    return structure(c, BASE_CONFIG, Counter())


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    yield db
    db.close()


class TestInitDb:
    def test_tables_created(self, conn):
        init_db(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "questions" in tables
        assert "session_scores" in tables

    def test_fts_table_created(self, conn):
        init_db(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "questions_fts" in tables

    def test_no_triggers(self, conn):
        """FTS is managed explicitly in upsert — no DB triggers needed."""
        init_db(conn)
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        assert triggers == []

    def test_idempotent(self, conn):
        init_db(conn)
        init_db(conn)  # should not raise


class TestToRow:
    def test_row_has_correct_id(self, conn):
        q = _make_question()
        row = _to_row(q)
        assert row[0] == q.id

    def test_payload_is_valid_json(self, conn):
        q = _make_question()
        row = _to_row(q)
        payload = json.loads(row[-1])
        assert payload["id"] == q.id
        assert "question" in payload

    def test_has_media_flag(self, conn):
        q = _make_question()
        row = _to_row(q)
        assert row[8] == 0  # has_media column

    def test_session_id_null_for_adhoc(self, conn):
        q = _make_question()
        row = _to_row(q)
        assert row[4] is None  # session_id


class TestUpsert:
    def test_question_stored(self, conn):
        init_db(conn)
        q = _make_question()
        count = upsert([q], conn)
        assert count == 1
        row = conn.execute("SELECT id FROM questions WHERE id = ?", (q.id,)).fetchone()
        assert row is not None

    def test_upsert_replaces_existing(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        # Upsert again — should not raise and count should still be 1
        upsert([q], conn)
        count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        assert count == 1

    def test_multiple_questions_stored(self, conn):
        init_db(conn)
        questions = [_make_question(timestamp_offset=i * 200) for i in range(3)]
        count = upsert(questions, conn)
        assert count == 3
        db_count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        assert db_count == 3

    def test_payload_round_trips(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        row = conn.execute("SELECT payload FROM questions WHERE id = ?", (q.id,)).fetchone()
        payload = json.loads(row[0])
        assert payload["question"]["text"] == q.question.text
        assert payload["answer"]["text"] == q.answer.text

    def test_returns_total_count(self, conn):
        init_db(conn)
        questions = [_make_question(timestamp_offset=i * 200) for i in range(5)]
        count = upsert(questions, conn)
        assert count == 5

    def test_indexed_columns_populated(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        row = conn.execute(
            "SELECT date, asker, solver, extraction_confidence FROM questions WHERE id = ?",
            (q.id,)
        ).fetchone()
        assert row[0] == "2025-09-23"
        assert row[1] == "Pavan"
        assert row[2] == "Aditi"
        assert row[3] == "high"


class TestFTS:
    def test_fts_search_after_insert(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        results = conn.execute(
            "SELECT id FROM questions_fts WHERE questions_fts MATCH 'question_text:Corn'"
        ).fetchall()
        assert len(results) == 1
        assert results[0][0] == q.id

    def test_fts_answer_searchable(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        results = conn.execute(
            "SELECT id FROM questions_fts WHERE questions_fts MATCH 'answer_text:trade'"
        ).fetchall()
        assert len(results) == 1

    def test_fts_updated_after_replace(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        # Re-upsert (INSERT OR REPLACE fires delete + insert triggers)
        upsert([q], conn)
        results = conn.execute(
            "SELECT id FROM questions_fts WHERE questions_fts MATCH 'question_text:Corn'"
        ).fetchall()
        assert len(results) == 1  # not doubled

    def test_fts_no_match_returns_empty(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        results = conn.execute(
            "SELECT id FROM questions_fts WHERE questions_fts MATCH 'question_text:XYZnonexistent'"
        ).fetchall()
        assert results == []


class TestSessionScores:
    def test_per_question_scores_stored(self, conn):
        init_db(conn)
        q = _make_session_question(scores_after=[
            {"username": "Akshay", "score": 2},
            {"username": "Aditi", "score": 1},
        ])
        upsert([q], conn)
        rows = conn.execute(
            "SELECT username, score FROM session_scores WHERE after_question_id = ?",
            (q.id,)
        ).fetchall()
        assert len(rows) == 2
        assert {r[0] for r in rows} == {"Akshay", "Aditi"}

    def test_no_scores_for_adhoc(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        rows = conn.execute("SELECT * FROM session_scores").fetchall()
        assert rows == []

    def test_final_scores_stored_with_null_question_id(self, conn):
        init_db(conn)
        upsert_session_final_scores(
            "2025-09-23-pratik",
            [{"username": "Akshay", "score": 5}, {"username": "Aditi", "score": 3}],
            conn
        )
        rows = conn.execute(
            "SELECT username, score FROM session_scores WHERE after_question_id IS NULL"
        ).fetchall()
        assert len(rows) == 2

    def test_score_upsert_is_idempotent(self, conn):
        init_db(conn)
        q = _make_session_question(scores_after=[{"username": "Akshay", "score": 2}])
        upsert([q], conn)
        upsert([q], conn)
        rows = conn.execute(
            "SELECT * FROM session_scores WHERE after_question_id = ?", (q.id,)
        ).fetchall()
        assert len(rows) == 1


class TestUpdateState:
    def test_state_file_created(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "pipeline_state.json"
            update_state([q], conn, state_path)
            assert state_path.exists()

    def test_last_stored_date_set(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "pipeline_state.json"
            update_state([q], conn, state_path)
            state = json.loads(state_path.read_text())
            assert state["last_stored_date"] == "2025-09-23"

    def test_total_questions_in_state(self, conn):
        init_db(conn)
        questions = [_make_question(timestamp_offset=i * 200) for i in range(3)]
        upsert(questions, conn)
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "pipeline_state.json"
            update_state(questions, conn, state_path)
            state = json.loads(state_path.read_text())
            assert state["total_questions"] == 3

    def test_existing_state_preserved(self, conn):
        init_db(conn)
        q = _make_question()
        upsert([q], conn)
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "pipeline_state.json"
            state_path.write_text(json.dumps({
                "last_stored_date": "2025-09-22",
                "last_exported_date": "2025-09-22",
                "total_questions": 10,
            }))
            update_state([q], conn, state_path)
            state = json.loads(state_path.read_text())
            # last_exported_date should be untouched
            assert state["last_exported_date"] == "2025-09-22"
            # last_stored_date updated to newer date
            assert state["last_stored_date"] == "2025-09-23"


class TestRun:
    def test_run_stores_questions(self, conn):
        q = _make_question()
        count = run([q], conn)
        assert count == 1
        row = conn.execute("SELECT id FROM questions WHERE id = ?", (q.id,)).fetchone()
        assert row is not None

    def test_run_inits_schema(self, conn):
        q = _make_question()
        run([q], conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "questions" in tables
        assert "questions_fts" in tables

    def test_run_empty_input(self, conn):
        count = run([], conn)
        assert count == 0

    def test_run_updates_state_file(self, conn):
        q = _make_question()
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "pipeline_state.json"
            run([q], conn, state_path=state_path)
            assert state_path.exists()
            state = json.loads(state_path.read_text())
            assert state["last_stored_date"] == "2025-09-23"

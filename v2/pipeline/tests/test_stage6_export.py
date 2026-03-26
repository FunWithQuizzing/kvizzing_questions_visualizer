"""Tests for Stage 6 — Export."""

import json
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))

from stages.stage5_store import run as store_run, upsert_session_final_scores
from stages.stage6_export import (
    build_questions,
    build_sessions,
    build_stats,
    build_tags,
    build_members,
    run,
)
from stages.stage3_structure import structure
from schema import KVizzingQuestion, TopicCategory

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
        {"timestamp": "2025-09-23T19:26:01Z", "username": "Akshay", "text": "Tariffs?", "role": "attempt", "is_correct": False},
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
        ans_ts = (base + timedelta(seconds=timestamp_offset + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["answer_timestamp"] = ans_ts
        c["discussion"] = [
            {"timestamp": ans_ts, "username": "Aditi", "text": "Free trade!", "role": "attempt", "is_correct": True},
        ]
    return structure(c, BASE_CONFIG, Counter())


def _make_session_question(
    timestamp_offset: int = 0,
    quizmaster: str = "pratik.s.chandarana",
    question_number: int = 1,
    scores_after=None,
) -> KVizzingQuestion:
    import copy
    from datetime import datetime, timezone, timedelta
    c = copy.deepcopy(_BASE_CANDIDATE)
    c["is_session_question"] = True
    c["session_quizmaster"] = quizmaster
    c["session_theme"] = "Movies"
    c["session_question_number"] = question_number
    if scores_after is not None:
        c["scores_after"] = scores_after
    if timestamp_offset:
        base = datetime(2025, 9, 23, 19, 25, 40, tzinfo=timezone.utc)
        new_ts = (base + timedelta(seconds=timestamp_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["question_timestamp"] = new_ts
        ans_ts = (base + timedelta(seconds=timestamp_offset + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["answer_timestamp"] = ans_ts
        c["discussion"] = [
            {"timestamp": ans_ts, "username": "Aditi", "text": "Free trade!", "role": "attempt", "is_correct": True},
        ]
    return structure(c, BASE_CONFIG, Counter())


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def db_with_questions(db):
    """DB pre-loaded with 2 ad-hoc + 2 session questions."""
    q1 = _make_question(timestamp_offset=0)
    q2 = _make_question(timestamp_offset=200)
    sq1 = _make_session_question(
        timestamp_offset=400,
        question_number=1,
        scores_after=[{"username": "Akshay", "score": 1}],
    )
    sq2 = _make_session_question(
        timestamp_offset=600,
        question_number=2,
        scores_after=[{"username": "Akshay", "score": 2}],
    )
    store_run([q1, q2, sq1, sq2], db)
    return db, [q1, q2, sq1, sq2]


class TestBuildQuestions:
    def test_returns_all_questions(self, db_with_questions):
        db, questions = db_with_questions
        result = build_questions(db)
        assert len(result) == 4

    def test_sorted_by_timestamp(self, db_with_questions):
        db, _ = db_with_questions
        result = build_questions(db)
        timestamps = [q["question"]["timestamp"] for q in result]
        assert timestamps == sorted(timestamps)

    def test_scores_after_populated_for_session_questions(self, db_with_questions):
        db, questions = db_with_questions
        result = build_questions(db)
        session_qs = [q for q in result if q.get("session")]
        assert all(q["scores_after"] is not None for q in session_qs)

    def test_scores_after_null_for_adhoc(self, db_with_questions):
        db, _ = db_with_questions
        result = build_questions(db)
        adhoc_qs = [q for q in result if not q.get("session")]
        assert all(q["scores_after"] is None for q in adhoc_qs)

    def test_scores_after_values_correct(self, db_with_questions):
        db, questions = db_with_questions
        result = build_questions(db)
        sq1_result = next(q for q in result if q.get("session") and q["session"]["question_number"] == 1)
        assert sq1_result["scores_after"][0]["username"] == "Akshay"
        assert sq1_result["scores_after"][0]["score"] == 1

    def test_payload_fields_intact(self, db_with_questions):
        db, _ = db_with_questions
        result = build_questions(db)
        for q in result:
            assert "id" in q
            assert "question" in q
            assert "answer" in q
            assert "stats" in q


class TestBuildSessions:
    def test_returns_session_list(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert len(sessions) == 1
        assert sessions[0]["id"] == "2025-09-23-pratik"

    def test_question_count_correct(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["question_count"] == 2

    def test_quizmaster_populated(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["quizmaster"] == "pratik.s.chandarana"

    def test_theme_populated(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["theme"] == "Movies"

    def test_avg_stats_computed(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["avg_time_to_answer_seconds"] == 90.0
        assert sessions[0]["avg_wrong_attempts"] == 0.0

    def test_participant_count(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["participant_count"] == 1  # only Aditi attempts

    def test_final_scores_included(self, db_with_questions):
        db, _ = db_with_questions
        upsert_session_final_scores(
            "2025-09-23-pratik",
            [{"username": "Akshay", "score": 5}],
            db,
        )
        sessions = build_sessions(db)
        assert sessions[0]["scores"] is not None
        assert sessions[0]["scores"][0]["score"] == 5

    def test_no_final_scores_is_none(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["scores"] is None

    def test_empty_db_returns_empty(self, db):
        store_run([], db)
        sessions = build_sessions(db)
        assert sessions == []


class TestBuildStats:
    def test_total_questions_count(self):
        q1 = json.loads(_make_question().model_dump_json())
        q2 = json.loads(_make_question(timestamp_offset=200).model_dump_json())
        stats = build_stats([q1, q2])
        assert stats["total_questions"] == 2

    def test_total_sessions_count(self, db_with_questions):
        db, _ = db_with_questions
        questions = build_questions(db)
        stats = build_stats(questions)
        assert stats["total_sessions"] == 1

    def test_topic_distribution(self):
        q = json.loads(_make_question().model_dump_json())
        q["question"]["topic"] = "history"
        stats = build_stats([q])
        assert stats["topic_distribution"]["history"] == 1

    def test_difficulty_distribution(self):
        q = json.loads(_make_question().model_dump_json())
        q["stats"]["difficulty"] = "easy"
        stats = build_stats([q])
        assert stats["difficulty_distribution"]["easy"] == 1

    def test_session_activity_by_date(self, db_with_questions):
        db, _ = db_with_questions
        questions = build_questions(db)
        stats = build_stats(questions)
        assert len(stats["session_activity"]) >= 1
        entry = stats["session_activity"][0]
        assert "date" in entry
        assert "question_count" in entry

    def test_empty_input(self):
        stats = build_stats([])
        assert stats["total_questions"] == 0
        assert stats["total_sessions"] == 0


class TestBuildTags:
    def test_tag_index_built(self):
        q = json.loads(_make_question().model_dump_json())
        q["question"]["tags"] = ["economics", "uk"]
        tags = build_tags([q])
        assert "economics" in tags
        assert q["id"] in tags["economics"]

    def test_multiple_questions_same_tag(self):
        q1 = json.loads(_make_question().model_dump_json())
        q2 = json.loads(_make_question(timestamp_offset=200).model_dump_json())
        q1["question"]["tags"] = ["history"]
        q2["question"]["tags"] = ["history"]
        tags = build_tags([q1, q2])
        assert len(tags["history"]) == 2

    def test_no_tags_returns_empty(self):
        q = json.loads(_make_question().model_dump_json())
        q["question"]["tags"] = []
        tags = build_tags([q])
        assert tags == {}

    def test_empty_input(self):
        assert build_tags([]) == {}


class TestBuildMembers:
    def test_asker_counted(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        pavan = next(m for m in members if m["username"] == "Pavan")
        assert pavan["questions_asked"] == 1

    def test_solver_counted(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        aditi = next(m for m in members if m["username"] == "Aditi")
        assert aditi["questions_solved"] == 1

    def test_attempts_counted(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        akshay = next((m for m in members if m["username"] == "Akshay"), None)
        assert akshay is not None
        assert akshay["total_attempts"] == 1

    def test_config_display_name_applied(self):
        q = json.loads(_make_question().model_dump_json())
        config = [{"username": "Pavan", "display_name": "Pavan P", "color": "#FF0000", "avatar_url": None}]
        members = build_members([q], config)
        pavan = next(m for m in members if m["username"] == "Pavan")
        assert pavan["display_name"] == "Pavan P"
        assert pavan["color"] == "#FF0000"

    def test_unknown_member_gets_username_as_display_name(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        pavan = next(m for m in members if m["username"] == "Pavan")
        assert pavan["display_name"] == "Pavan"
        assert pavan["color"] is None

    def test_avg_solve_time_computed(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        aditi = next(m for m in members if m["username"] == "Aditi")
        assert aditi["avg_solve_time_seconds"] == 90.0

    def test_sessions_hosted_counted(self, db_with_questions):
        db, _ = db_with_questions
        questions = build_questions(db)
        members = build_members(questions, [])
        pratik = next(m for m in members if m["username"] == "pratik.s.chandarana")
        assert pratik["sessions_hosted"] == 1


class TestRun:
    def test_creates_all_json_files(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run(db, output_dir)
            assert (output_dir / "questions.json").exists()
            assert (output_dir / "sessions.json").exists()
            assert (output_dir / "stats.json").exists()
            assert (output_dir / "tags.json").exists()
            assert (output_dir / "members.json").exists()

    def test_questions_json_is_valid(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run(db, output_dir)
            data = json.loads((output_dir / "questions.json").read_text())
            assert isinstance(data, list)
            assert len(data) == 4

    def test_state_file_updated(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            state_path = output_dir / "pipeline_state.json"
            run(db, output_dir, state_path=state_path)
            state = json.loads(state_path.read_text())
            assert state["last_exported_date"] == "2025-09-23"

    def test_returns_counts(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            counts = run(db, Path(tmpdir))
            assert counts["questions"] == 4
            assert counts["sessions"] == 1

    def test_members_config_used(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            members_config = [{"username": "Pavan", "display_name": "Pavan P", "color": "#F00", "avatar_url": None}]
            cfg_path = output_dir / "members.json.config"
            cfg_path.write_text(json.dumps(members_config))
            run(db, output_dir, members_config_path=cfg_path)
            members = json.loads((output_dir / "members.json").read_text())
            pavan = next(m for m in members if m["username"] == "Pavan")
            assert pavan["display_name"] == "Pavan P"

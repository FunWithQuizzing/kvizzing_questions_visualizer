"""Tests for Stage 3 — Structure."""

import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))

from stages.stage3_structure import structure, run, _make_id, _compute_stats
from schema import KVizzingQuestion, Difficulty, QuestionType

BASE_CONFIG = {
    "stage3": {
        "difficulty": {
            "easy_max_wrong_attempts": 0,
            "medium_max_wrong_attempts": 3,
        }
    }
}

# Minimal valid raw candidate
_BASE_CANDIDATE = {
    "question_timestamp": "2025-09-23T19:25:40Z",
    "question_text": "What economic principle was established by the repeal of the Corn Laws?",
    "question_asker": "Pavan Pamidimarri",
    "has_media": False,
    "is_session_question": False,
    "session_quizmaster": None,
    "session_theme": None,
    "session_question_number": None,
    "answer_text": "Free trade",
    "answer_solver": "Aditi Bapat",
    "answer_timestamp": "2025-09-23T19:27:10Z",
    "answer_confirmed": True,
    "confirmation_text": "Bingo!",
    "answer_is_collaborative": False,
    "answer_parts": None,
    "discussion": [
        {"timestamp": "2025-09-23T19:26:01Z", "username": "Akshay", "text": "Tariffs?", "role": "attempt", "is_correct": False},
        {"timestamp": "2025-09-23T19:26:15Z", "username": "Pavan Pamidimarri", "text": "Nope, think broader", "role": "hint", "is_correct": None},
        {"timestamp": "2025-09-23T19:27:10Z", "username": "Aditi Bapat", "text": "Free trade!", "role": "attempt", "is_correct": True},
        {"timestamp": "2025-09-23T19:27:20Z", "username": "Pavan Pamidimarri", "text": "Bingo!", "role": "confirmation", "is_correct": None},
    ],
    "scores_after": None,
    "extraction_confidence": "high",
}


def _base() -> dict:
    import copy
    return copy.deepcopy(_BASE_CANDIDATE)


class TestMakeId:
    def test_basic_id_format(self):
        counter = Counter()
        id_ = _make_id("2025-09-23T19:25:40Z", counter)
        assert id_ == "2025-09-23-192540"

    def test_collision_appends_digit(self):
        counter = Counter()
        id1 = _make_id("2025-09-23T19:25:40Z", counter)
        id2 = _make_id("2025-09-23T19:25:40Z", counter)
        id3 = _make_id("2025-09-23T19:25:40Z", counter)
        assert id1 == "2025-09-23-192540"
        assert id2 == "2025-09-23-1925402"
        assert id3 == "2025-09-23-1925403"

    def test_different_timestamps_no_collision(self):
        counter = Counter()
        id1 = _make_id("2025-09-23T19:25:40Z", counter)
        id2 = _make_id("2025-09-23T19:25:41Z", counter)
        assert id1 != id2
        assert not id2.endswith("2")


class TestComputeStats:
    def test_wrong_attempts_counted(self):
        discussion = [
            {"role": "attempt", "is_correct": False},
            {"role": "attempt", "is_correct": False},
            {"role": "attempt", "is_correct": True},
        ]
        stats = _compute_stats(discussion, BASE_CONFIG)
        assert stats["wrong_attempts"] == 2

    def test_hints_counted(self):
        discussion = [
            {"role": "hint", "is_correct": None},
            {"role": "hint", "is_correct": None},
            {"role": "attempt", "is_correct": True},
        ]
        stats = _compute_stats(discussion, BASE_CONFIG)
        assert stats["hints_given"] == 2

    def test_difficulty_easy(self):
        discussion = [{"role": "attempt", "is_correct": True, "username": "x"}]
        stats = _compute_stats(discussion, BASE_CONFIG)
        assert stats["difficulty"] == Difficulty.easy

    def test_difficulty_medium(self):
        discussion = [
            {"role": "attempt", "is_correct": False, "username": "x"},
            {"role": "attempt", "is_correct": False, "username": "y"},
            {"role": "attempt", "is_correct": True, "username": "z"},
        ]
        stats = _compute_stats(discussion, BASE_CONFIG)
        assert stats["difficulty"] == Difficulty.medium

    def test_difficulty_hard(self):
        discussion = [
            {"role": "attempt", "is_correct": False, "username": "a"},
            {"role": "attempt", "is_correct": False, "username": "b"},
            {"role": "attempt", "is_correct": False, "username": "c"},
            {"role": "attempt", "is_correct": False, "username": "d"},
            {"role": "attempt", "is_correct": True, "username": "e"},
        ]
        stats = _compute_stats(discussion, BASE_CONFIG)
        assert stats["difficulty"] == Difficulty.hard

    def test_unique_participants(self):
        discussion = [
            {"role": "attempt", "is_correct": False, "username": "A"},
            {"role": "attempt", "is_correct": False, "username": "A"},  # same person
            {"role": "attempt", "is_correct": True, "username": "B"},
        ]
        stats = _compute_stats(discussion, BASE_CONFIG)
        assert stats["unique_participants"] == 2


class TestStructure:
    def test_valid_candidate_produces_question(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        assert obj is not None
        assert isinstance(obj, KVizzingQuestion)

    def test_id_is_timestamp_based(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        assert obj.id == "2025-09-23-192540"

    def test_date_derived_from_timestamp(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        from datetime import date
        assert obj.date == date(2025, 9, 23)

    def test_time_to_answer_computed(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        # 19:27:10 - 19:25:40 = 90 seconds
        assert obj.stats.time_to_answer_seconds == 90

    def test_wrong_attempts_computed(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        assert obj.stats.wrong_attempts == 1

    def test_hints_given_computed(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        assert obj.stats.hints_given == 1

    def test_unanswered_difficulty_is_none(self):
        c = _base()
        c["answer_text"] = None
        c["answer_confirmed"] = False
        obj = structure(c, BASE_CONFIG, Counter())
        assert obj.stats.difficulty is None

    def test_missing_question_text_raises(self):
        c = _base()
        del c["question_text"]
        with pytest.raises((KeyError, ValueError)):
            structure(c, BASE_CONFIG, Counter())

    def test_session_populated_when_present(self):
        c = _base()
        c["is_session_question"] = True
        c["session_quizmaster"] = "pratik.s.chandarana"
        c["session_theme"] = "Hollywood Movies"
        c["session_question_number"] = 3
        obj = structure(c, BASE_CONFIG, Counter())
        assert obj is not None
        assert obj.session is not None
        assert obj.session.quizmaster == "pratik.s.chandarana"
        assert obj.session.theme == "Hollywood Movies"
        assert obj.session.question_number == 3
        # Session ID uses first name component (split on space or dot)
        assert obj.session.id == "2025-09-23-pratik"

    def test_session_slug_split_on_space(self):
        c = _base()
        c["is_session_question"] = True
        c["session_quizmaster"] = "Pavan Pamidimarri"
        obj = structure(c, BASE_CONFIG, Counter())
        assert obj.session.id == "2025-09-23-pavan"

    def test_session_none_for_adhoc(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        assert obj.session is None

    def test_question_type_inferred(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        assert obj.question.type == QuestionType.factual

    def test_multi_part_type_when_parts_present(self):
        c = _base()
        c["answer_parts"] = [
            {"label": "X", "text": "Part one", "solver": "Akshay"},
            {"label": "Y", "text": "Part two", "solver": "Aditi Bapat"},
        ]
        obj = structure(c, BASE_CONFIG, Counter())
        assert obj is not None
        assert obj.question.type == QuestionType.multi_part
        assert len(obj.answer.parts) == 2


class TestScoresAfter:
    """scores_after field — added recently; covering all cases."""

    def test_scores_after_null_when_not_present(self):
        obj = structure(_base(), BASE_CONFIG, Counter())
        assert obj.scores_after is None

    def test_scores_after_populated_when_present(self):
        c = _base()
        c["is_session_question"] = True
        c["session_quizmaster"] = "pratik.s.chandarana"
        c["session_question_number"] = 1
        c["scores_after"] = [
            {"username": "Akshay", "score": 3},
            {"username": "Aditi Bapat", "score": 1},
        ]
        obj = structure(c, BASE_CONFIG, Counter())
        assert obj is not None
        assert obj.scores_after is not None
        assert len(obj.scores_after) == 2
        usernames = {s.username for s in obj.scores_after}
        assert usernames == {"Akshay", "Aditi Bapat"}

    def test_scores_after_values_correct(self):
        c = _base()
        c["is_session_question"] = True
        c["session_quizmaster"] = "pratik.s.chandarana"
        c["session_question_number"] = 1
        c["scores_after"] = [{"username": "Akshay", "score": 5}]
        obj = structure(c, BASE_CONFIG, Counter())
        assert obj.scores_after[0].score == 5

    def test_scores_after_empty_list_becomes_none(self):
        c = _base()
        c["scores_after"] = []
        obj = structure(c, BASE_CONFIG, Counter())
        # Empty list → _map_scores_after returns None
        assert obj.scores_after is None

    def test_scores_after_cleared_for_adhoc_questions(self):
        """Stage 3 must null out scores_after for non-session questions even if LLM set it."""
        c = _base()
        c["is_session_question"] = False
        c["scores_after"] = [{"username": "Akshay", "score": 1}]
        obj = structure(c, BASE_CONFIG, Counter())
        assert obj is not None
        assert obj.scores_after is None


class TestRun:
    def test_valid_candidates_structured(self):
        results = run([_base()], BASE_CONFIG)
        assert len(results) == 1

    def test_invalid_candidate_skipped(self):
        bad = {"question_timestamp": "not-a-date"}
        results = run([bad, _base()], BASE_CONFIG)
        assert len(results) == 1

    def test_errors_logged_to_dir(self):
        bad = {"question_timestamp": "not-a-date"}
        with tempfile.TemporaryDirectory() as tmpdir:
            errors_dir = Path(tmpdir)
            run([bad], BASE_CONFIG, errors_dir=errors_dir)
            error_files = list(errors_dir.glob("*_errors.json"))
            assert len(error_files) == 1

    def test_multiple_candidates_collision_ids_unique(self):
        # Two candidates with the same timestamp
        c1, c2 = _base(), _base()
        results = run([c1, c2], BASE_CONFIG)
        ids = [r.id for r in results]
        assert len(ids) == len(set(ids))

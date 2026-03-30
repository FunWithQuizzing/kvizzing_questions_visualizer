"""Tests for Stage 4 — Enrich."""

import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))

from stages.stage4_enrich import enrich, run, _apply_enrichment, _build_batch_prompt
from stages.stage3_structure import structure
from schema import KVizzingQuestion, TopicCategory

BASE_CONFIG = {
    "stage3": {
        "difficulty": {
            "easy_max_wrong_attempts": 0,
            "medium_max_wrong_attempts": 3,
        }
    },
    "stage4": {
        "llm_model": "claude-sonnet-4-6",
        "llm_batch_size": 5,
        "llm_max_retries": 2,
        "llm_retry_base_delay_seconds": 0,
    },
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


def _make_question(timestamp_offset: int = 0, topic=None) -> KVizzingQuestion:
    import copy
    from datetime import datetime, timezone, timedelta
    c = copy.deepcopy(_BASE_CANDIDATE)
    if timestamp_offset:
        base = datetime(2025, 9, 23, 19, 25, 40, tzinfo=timezone.utc)
        new_ts = (base + timedelta(seconds=timestamp_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["question_timestamp"] = new_ts
        c["answer_timestamp"] = (base + timedelta(seconds=timestamp_offset + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["discussion"][0]["timestamp"] = c["answer_timestamp"]
    q = structure(c, BASE_CONFIG, Counter())
    if topic is not None:
        updated = q.question.model_copy(update={"topics": [topic]})
        q = q.model_copy(update={"question": updated})
    return q


def _mock_llm(responses: list[list[dict]]):
    """Build a mock LLM client that returns successive responses."""
    call_count = [0]
    mock = MagicMock()

    def create(**kwargs):
        idx = call_count[0]
        call_count[0] += 1
        payload = responses[idx] if idx < len(responses) else []
        response = SimpleNamespace(
            content=[SimpleNamespace(text=__import__("json").dumps(payload))]
        )
        return response

    mock.messages.create.side_effect = create
    return mock


class TestApplyEnrichment:
    def test_topic_applied(self):
        q = _make_question()
        enriched = _apply_enrichment(q, {"id": q.id, "topic": "history", "tags": ["economics"]})
        assert enriched.question.topics == [TopicCategory.history]

    def test_tags_applied(self):
        q = _make_question()
        enriched = _apply_enrichment(q, {"id": q.id, "topic": "history", "tags": ["india", "colonial"]})
        assert enriched.question.tags == ["india", "colonial"]

    def test_unknown_topic_falls_back_to_general(self):
        q = _make_question()
        enriched = _apply_enrichment(q, {"id": q.id, "topic": "bogus_category", "tags": []})
        assert enriched.question.topics == [TopicCategory.general]

    def test_original_question_not_mutated(self):
        q = _make_question()
        _apply_enrichment(q, {"id": q.id, "topic": "science", "tags": ["physics"]})
        assert not q.question.topics


class TestBuildBatchPrompt:
    def test_contains_question_text(self):
        q = _make_question()
        prompt = _build_batch_prompt([q])
        assert "Corn Laws" in prompt

    def test_contains_id(self):
        q = _make_question()
        prompt = _build_batch_prompt([q])
        assert q.id in prompt

    def test_valid_json(self):
        import json
        q = _make_question()
        items = json.loads(_build_batch_prompt([q]))
        assert isinstance(items, list)
        assert items[0]["id"] == q.id


class TestEnrich:
    def test_topic_assigned(self):
        q = _make_question()
        llm = _mock_llm([[{"id": q.id, "topic": "history", "tags": ["economics"]}]])
        results = enrich([q], BASE_CONFIG, llm)
        assert results[0].question.topics == [TopicCategory.history]

    def test_tags_assigned(self):
        q = _make_question()
        llm = _mock_llm([[{"id": q.id, "topic": "history", "tags": ["economics", "uk"]}]])
        results = enrich([q], BASE_CONFIG, llm)
        assert results[0].question.tags == ["economics", "uk"]

    def test_already_enriched_skipped(self):
        q = _make_question(topic=TopicCategory.science)
        llm = _mock_llm([])
        results = enrich([q], BASE_CONFIG, llm)
        # LLM not called — topic unchanged
        assert results[0].question.topics == [TopicCategory.science]
        llm.messages.create.assert_not_called()

    def test_order_preserved(self):
        q1 = _make_question(timestamp_offset=0)
        q2 = _make_question(timestamp_offset=200)
        q3 = _make_question(timestamp_offset=400)
        llm = _mock_llm([[
            {"id": q1.id, "topic": "history", "tags": []},
            {"id": q2.id, "topic": "science", "tags": []},
            {"id": q3.id, "topic": "sports", "tags": []},
        ]])
        results = enrich([q1, q2, q3], BASE_CONFIG, llm)
        assert results[0].id == q1.id
        assert results[1].id == q2.id
        assert results[2].id == q3.id

    def test_batching_splits_correctly(self):
        """With batch_size=5, 7 questions should produce 2 LLM calls."""
        questions = [_make_question(timestamp_offset=i * 200) for i in range(7)]
        responses = [
            [{"id": q.id, "topic": "general", "tags": []} for q in questions[:5]],
            [{"id": q.id, "topic": "general", "tags": []} for q in questions[5:]],
        ]
        llm = _mock_llm(responses)
        results = enrich(questions, BASE_CONFIG, llm)
        assert llm.messages.create.call_count == 2
        assert len(results) == 7

    def test_llm_failure_keeps_question_unchanged(self):
        """If LLM returns nothing for a question, it passes through unenriched."""
        q = _make_question()
        llm = _mock_llm([[]])  # LLM returns empty array
        results = enrich([q], BASE_CONFIG, llm)
        assert not results[0].question.topics

    def test_partial_llm_response(self):
        """LLM returns result for only some questions in the batch."""
        q1 = _make_question(timestamp_offset=0)
        q2 = _make_question(timestamp_offset=200)
        llm = _mock_llm([[{"id": q1.id, "topic": "history", "tags": []}]])
        results = enrich([q1, q2], BASE_CONFIG, llm)
        assert results[0].question.topics == [TopicCategory.history]
        assert not results[1].question.topics  # not in response

    def test_mixed_enriched_and_unenriched(self):
        """Already-enriched questions are preserved; unenriched ones get enriched."""
        q_done = _make_question(timestamp_offset=0, topic=TopicCategory.sports)
        q_todo = _make_question(timestamp_offset=200)
        llm = _mock_llm([[{"id": q_todo.id, "topic": "science", "tags": ["physics"]}]])
        results = enrich([q_done, q_todo], BASE_CONFIG, llm)
        assert results[0].question.topics == [TopicCategory.sports]
        assert results[1].question.topics == [TopicCategory.science]


class TestRun:
    def test_no_llm_returns_unchanged(self):
        q = _make_question()
        results = run([q], BASE_CONFIG, llm_client=None)
        assert not results[0].question.topics
        assert results[0].id == q.id

    def test_with_llm_enriches(self):
        q = _make_question()
        llm = _mock_llm([[{"id": q.id, "topic": "geography", "tags": ["europe"]}]])
        results = run([q], BASE_CONFIG, llm_client=llm)
        assert results[0].question.topics == [TopicCategory.geography]

    def test_empty_input(self):
        results = run([], BASE_CONFIG, llm_client=None)
        assert results == []

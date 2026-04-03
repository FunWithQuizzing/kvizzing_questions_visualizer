"""Tests for Stage 2 — Extract (heuristic pre-filter; LLM calls are mocked)."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.stage1_parse import run as parse
from stages.stage2_extract import prefilter, run, detect_session_scores

BASE_CONFIG = {
    "source_timezone": "America/Chicago",
    "stage1": {"locale_formats": ["%m/%d/%y, %H:%M:%S", "%m/%d/%y, %I:%M:%S %p", "%d/%m/%Y, %H:%M:%S"]},
    "stage2": {
        "extraction_window_messages": 40,
        "heuristic_reply_window_minutes": 15,
        "heuristic_min_replies": 2,
    },
    "stage4": {
        "llm_model": "claude-sonnet-4-6",
        "llm_batch_size": 15,
        "llm_max_retries": 3,
        "llm_retry_base_delay_seconds": 2,
    },
}


def _parse(fixture_name: str) -> list[dict]:
    lines = (FIXTURES / fixture_name).read_text(encoding="utf-8").splitlines(keepends=True)
    return parse(lines, BASE_CONFIG)


def _mock_llm(response_pairs: list[dict]):
    """Return a mock LLM client that returns the given pairs."""
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(response_pairs))]
    client.messages.create.return_value = msg
    return client


class TestPrefilter:
    def test_question_with_replies_is_candidate(self):
        msgs = _parse("chat_us_locale.txt")
        indices = prefilter(msgs, BASE_CONFIG)
        assert len(indices) > 0

    def test_plain_chat_no_candidates(self):
        msgs = _parse("chat_no_questions.txt")
        indices = prefilter(msgs, BASE_CONFIG)
        assert indices == []

    def test_session_marker_always_included(self):
        msgs = _parse("chat_session.txt")
        indices = prefilter(msgs, BASE_CONFIG)
        # The ###Quiz Start message should be included
        assert any("Quiz Start" in msgs[i]["text"] for i in indices)

    def test_question_without_enough_replies_excluded(self):
        # Only one reply — below min_replies=2
        msgs = [
            {"timestamp": "2025-09-23T19:00:00Z", "username": "Asker", "text": "What is 2+2?", "has_media": False},
            {"timestamp": "2025-09-23T19:01:00Z", "username": "User1", "text": "4", "has_media": False},
        ]
        indices = prefilter(msgs, BASE_CONFIG)
        assert indices == []

    def test_question_with_two_replies_included(self):
        msgs = [
            {"timestamp": "2025-09-23T19:00:00Z", "username": "Asker", "text": "What is 2+2?", "has_media": False},
            {"timestamp": "2025-09-23T19:01:00Z", "username": "User1", "text": "4", "has_media": False},
            {"timestamp": "2025-09-23T19:01:30Z", "username": "User2", "text": "Four", "has_media": False},
        ]
        indices = prefilter(msgs, BASE_CONFIG)
        assert 0 in indices

    def test_q_prefix_detected(self):
        msgs = [
            {"timestamp": "2025-09-23T19:00:00Z", "username": "QM", "text": "Q1. Name the capital of France.", "has_media": False},
            {"timestamp": "2025-09-23T19:01:00Z", "username": "User1", "text": "Paris", "has_media": False},
            {"timestamp": "2025-09-23T19:01:30Z", "username": "User2", "text": "Paris!", "has_media": False},
        ]
        indices = prefilter(msgs, BASE_CONFIG)
        assert 0 in indices

    def test_replies_outside_window_not_counted(self):
        """Replies after the window should not count toward min_replies."""
        msgs = [
            {"timestamp": "2025-09-23T19:00:00Z", "username": "Asker", "text": "What is 2+2?", "has_media": False},
            {"timestamp": "2025-09-23T19:20:00Z", "username": "User1", "text": "4", "has_media": False},
            {"timestamp": "2025-09-23T19:21:00Z", "username": "User2", "text": "Four", "has_media": False},
        ]
        indices = prefilter(msgs, BASE_CONFIG)
        assert indices == []


class TestExtract:
    def test_llm_called_once_per_day(self):
        """New architecture: one LLM call for all messages in a day."""
        msgs = _parse("chat_us_locale.txt")
        mock_pair = {
            "question_timestamp": "2025-09-23T19:25:40Z",
            "question_text": "Name this economic principle?",
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
            "discussion": [],
            "scores_after": None,
            "extraction_confidence": "high",
        }
        client = _mock_llm([mock_pair])
        result = run(msgs, BASE_CONFIG, llm_client=client)
        # Exactly one LLM call regardless of candidate count
        assert client.messages.create.call_count == 1
        assert len(result) == 1

    def test_llm_error_returns_empty(self):
        msgs = _parse("chat_us_locale.txt")
        client = MagicMock()
        client.messages.create.side_effect = Exception("API error")
        with pytest.raises(Exception, match="API error"):
            run(msgs, BASE_CONFIG, llm_client=client)

    def test_run_without_llm_returns_candidate_messages(self):
        """In test mode (no llm_client), run() returns candidate messages."""
        msgs = _parse("chat_us_locale.txt")
        result = run(msgs, BASE_CONFIG, llm_client=None)
        assert len(result) > 0
        assert all("timestamp" in r for r in result)

    def test_run_no_candidates_skips_llm(self):
        msgs = _parse("chat_no_questions.txt")
        client = MagicMock()
        result = run(msgs, BASE_CONFIG, llm_client=client)
        client.messages.create.assert_not_called()
        assert result == []

    def test_llm_rate_limit_retries(self):
        msgs = _parse("chat_us_locale.txt")
        client = MagicMock()
        # Fail twice with 429, succeed on third
        client.messages.create.side_effect = [
            Exception("HTTP 429 rate_limit"),
            Exception("HTTP 429 rate_limit"),
            MagicMock(content=[MagicMock(text="[]")]),
        ]
        config = {**BASE_CONFIG, "stage4": {**BASE_CONFIG["stage4"], "llm_retry_base_delay_seconds": 0}}
        result = run(msgs, config, llm_client=client)
        assert client.messages.create.call_count == 3
        assert result == []


class TestDetectSessionScores:
    def test_scores_extracted_when_present(self):
        msgs = _parse("chat_session.txt")
        scores = [{"username": "Akshay", "score": 1}, {"username": "Sushant", "score": 1}]
        client = _mock_llm({"found": True, "scores": scores})
        # Patch the LLM response for detect_session_scores
        client.messages.create.return_value.content[0].text = json.dumps(
            {"found": True, "scores": scores}
        )
        result = detect_session_scores(msgs, BASE_CONFIG, client)
        assert result == scores

    def test_no_scores_returns_none(self):
        msgs = _parse("chat_us_locale.txt")
        client = MagicMock()
        client.messages.create.return_value.content[0].text = json.dumps(
            {"found": False, "scores": None}
        )
        result = detect_session_scores(msgs, BASE_CONFIG, client)
        assert result is None

    def test_empty_messages_returns_none(self):
        result = detect_session_scores([], BASE_CONFIG, MagicMock())
        assert result is None

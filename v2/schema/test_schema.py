"""
Tests for the KVizzing schema.

Run with:
    python3 -m pytest test_schema.py -v
or:
    python3 test_schema.py
"""

import copy
import json
import pathlib
import re
import tempfile

import pytest
from pydantic import ValidationError

from schema import (
    KVizzingQuestion,
    MediaAttachment,
    MediaType,
    Answer,
    AnswerPart,
    DiscussionEntry,
    Highlights,
    Question,
    Session,
    Source,
    Stats,
    _inject,
)

HERE = pathlib.Path(__file__).parent
EXAMPLES: list[dict] = json.loads((HERE / "examples.json").read_text())


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_example(index: int) -> dict:
    """Return a deep copy of the example at 0-based index with _comment stripped."""
    ex = copy.deepcopy(EXAMPLES[index])
    return {k: v for k, v in ex.items() if k != "_comment"}


# ── Examples round-trip ───────────────────────────────────────────────────────

class TestExamplesValid:
    """All examples in examples.json must parse without error."""

    @pytest.mark.parametrize("index,description", [
        (0, "factual — single solver, confirmed, with reactions"),
        (1, "multi_part — single solver gets all parts"),
        (2, "visual — part of a structured quiz session"),
        (3, "connect — collaborative solve, no single solver"),
    ])
    def test_example_parses(self, index, description):
        obj = KVizzingQuestion.model_validate(load_example(index))
        assert obj is not None, f"Example {index} ({description}) failed to parse"

    def test_example_ids_are_unique(self):
        ids = [ex["id"] for ex in EXAMPLES]
        assert len(ids) == len(set(ids)), "Duplicate IDs in examples.json"

    def test_example_count(self):
        assert len(EXAMPLES) == 4


# ── ID format ─────────────────────────────────────────────────────────────────

class TestIdFormat:
    def _base(self) -> dict:
        return load_example(0)

    def test_valid_id_formats(self):
        for id_ in ["2025-09-23-001", "2026-03-16-007", "2099-12-31-999"]:
            ex = self._base()
            ex["id"] = id_
            KVizzingQuestion.model_validate(ex)  # must not raise

    def test_invalid_id_no_sequence(self):
        ex = self._base()
        ex["id"] = "2025-09-23"
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_invalid_id_wrong_separator(self):
        ex = self._base()
        ex["id"] = "2025/09/23/001"
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_invalid_id_letters(self):
        ex = self._base()
        ex["id"] = "2025-09-23-abc"
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)


# ── Stats constraints ─────────────────────────────────────────────────────────

class TestStatsConstraints:
    def _base(self) -> dict:
        return load_example(0)

    def test_negative_wrong_attempts_rejected(self):
        ex = self._base()
        ex["stats"]["wrong_attempts"] = -1
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_negative_hints_rejected(self):
        ex = self._base()
        ex["stats"]["hints_given"] = -1
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_negative_time_to_answer_rejected(self):
        ex = self._base()
        ex["stats"]["time_to_answer_seconds"] = -1
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_zero_unique_participants_rejected(self):
        ex = self._base()
        ex["stats"]["unique_participants"] = 0
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_zero_wrong_attempts_allowed(self):
        ex = self._base()
        ex["stats"]["wrong_attempts"] = 0
        KVizzingQuestion.model_validate(ex)  # must not raise

    def test_null_optional_stats_allowed(self):
        ex = self._base()
        ex["stats"]["time_to_answer_seconds"] = None
        ex["stats"]["unique_participants"] = None
        ex["stats"]["difficulty"] = None
        KVizzingQuestion.model_validate(ex)  # must not raise


# ── Enum validation ───────────────────────────────────────────────────────────

class TestEnums:
    def _base(self) -> dict:
        return load_example(0)

    def test_invalid_question_type_rejected(self):
        ex = self._base()
        ex["question"]["type"] = "visual"  # removed in schema redesign
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_invalid_difficulty_rejected(self):
        ex = self._base()
        ex["stats"]["difficulty"] = "extreme"
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_invalid_extraction_confidence_rejected(self):
        ex = self._base()
        ex["extraction_confidence"] = "certain"
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_invalid_discussion_role_rejected(self):
        ex = self._base()
        ex["discussion"][0]["role"] = "reaction"  # old name, removed
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_invalid_topic_rejected(self):
        ex = self._base()
        ex["question"]["topic"] = "politics"
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)


# ── Required fields ───────────────────────────────────────────────────────────

class TestRequiredFields:
    def _base(self) -> dict:
        return load_example(0)

    @pytest.mark.parametrize("field", ["id", "date", "question", "answer", "discussion", "stats", "extraction_confidence", "source"])
    def test_missing_root_field_rejected(self, field):
        ex = self._base()
        del ex[field]
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_missing_answer_confirmed_rejected(self):
        ex = self._base()
        del ex["answer"]["confirmed"]
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_missing_answer_is_collaborative_rejected(self):
        ex = self._base()
        del ex["answer"]["is_collaborative"]
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)


# ── Optional fields ───────────────────────────────────────────────────────────

class TestOptionalFields:
    def _base(self) -> dict:
        return load_example(0)

    def test_null_session_allowed(self):
        ex = self._base()
        ex["session"] = None
        KVizzingQuestion.model_validate(ex)

    def test_null_reactions_allowed(self):
        ex = self._base()
        ex["reactions"] = None
        KVizzingQuestion.model_validate(ex)

    def test_null_highlights_allowed(self):
        ex = self._base()
        ex["highlights"] = None
        KVizzingQuestion.model_validate(ex)

    def test_null_solver_allowed(self):
        """Collaborative questions have no single solver."""
        ex = load_example(3)  # connect/collaborative example
        assert ex["answer"]["solver"] is None
        KVizzingQuestion.model_validate(ex)

    def test_null_answer_text_allowed(self):
        ex = self._base()
        ex["answer"]["text"] = None
        ex["answer"]["confirmed"] = False
        KVizzingQuestion.model_validate(ex)

    def test_empty_tags_allowed(self):
        ex = self._base()
        ex["question"]["tags"] = []
        KVizzingQuestion.model_validate(ex)

    def test_null_topic_allowed(self):
        ex = self._base()
        ex["question"]["topic"] = None
        KVizzingQuestion.model_validate(ex)


# ── Highlights validator ──────────────────────────────────────────────────────

class TestHighlights:
    def _base(self) -> dict:
        return load_example(0)

    def test_zero_reaction_count_rejected(self):
        ex = self._base()
        ex["highlights"]["reaction_counts"]["❤️"] = 0
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_negative_reaction_count_rejected(self):
        ex = self._base()
        ex["highlights"]["reaction_counts"]["😂"] = -1
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_valid_reaction_counts_accepted(self):
        ex = self._base()
        ex["highlights"]["reaction_counts"] = {"🔥": 3, "😂": 1}
        ex["highlights"]["total_reactions"] = 4
        KVizzingQuestion.model_validate(ex)


# ── Session constraints ───────────────────────────────────────────────────────

class TestSession:
    def _base(self) -> dict:
        return load_example(2)  # session example

    def test_question_number_zero_rejected(self):
        ex = self._base()
        ex["session"]["question_number"] = 0
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_null_theme_allowed(self):
        ex = self._base()
        ex["session"]["theme"] = None
        KVizzingQuestion.model_validate(ex)


# ── Source constraints ────────────────────────────────────────────────────────

class TestSource:
    def _base(self) -> dict:
        return load_example(0)

    def test_pair_index_zero_rejected(self):
        ex = self._base()
        ex["source"]["pair_index"] = 0
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_pair_index_one_allowed(self):
        ex = self._base()
        ex["source"]["pair_index"] = 1
        KVizzingQuestion.model_validate(ex)


# ── README injection ──────────────────────────────────────────────────────────

class TestInject:
    def test_inject_replaces_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("before\n<!-- BEGIN:foo -->\nold content\n<!-- END:foo -->\nafter\n")
            path = pathlib.Path(f.name)
        _inject(path, "foo", "new content")
        result = path.read_text()
        assert "new content" in result
        assert "old content" not in result
        assert "before" in result
        assert "after" in result

    def test_inject_missing_marker_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("no markers here\n")
            path = pathlib.Path(f.name)
        with pytest.raises(ValueError, match="not found"):
            _inject(path, "nonexistent", "content")

    def test_inject_idempotent(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- BEGIN:bar -->\nold\n<!-- END:bar -->\n")
            path = pathlib.Path(f.name)
        _inject(path, "bar", "new")
        _inject(path, "bar", "new")  # second inject must not double-wrap
        result = path.read_text()
        assert result.count("<!-- BEGIN:bar -->") == 1
        assert result.count("<!-- END:bar -->") == 1
        assert result.count("new") == 1


# ── Media attachments ─────────────────────────────────────────────────────────

class TestMedia:
    def _base(self) -> dict:
        return load_example(2)  # visual question — has_media: true

    def test_has_media_true_with_null_media_allowed(self):
        """has_media=True + media=None is valid: file exists but not yet extracted."""
        ex = self._base()
        assert ex["question"]["has_media"] is True
        assert ex["question"].get("media") is None
        KVizzingQuestion.model_validate(ex)

    def test_has_media_true_with_media_populated(self):
        ex = self._base()
        ex["question"]["media"] = [
            {
                "type": "image",
                "url": "https://cdn.example.com/media/2026-03-16-007-q.jpg",
                "filename": "IMG-20260316-WA0007.jpg",
                "caption": None,
            }
        ]
        KVizzingQuestion.model_validate(ex)

    def test_all_media_types_accepted(self):
        ex = self._base()
        for media_type in ["image", "video", "audio", "document"]:
            ex["question"]["media"] = [{"type": media_type}]
            KVizzingQuestion.model_validate(ex)

    def test_invalid_media_type_rejected(self):
        ex = self._base()
        ex["question"]["media"] = [{"type": "gif"}]
        with pytest.raises(ValidationError):
            KVizzingQuestion.model_validate(ex)

    def test_media_all_optional_fields_null(self):
        """url, filename, caption are all optional."""
        ex = self._base()
        ex["question"]["media"] = [{"type": "image"}]
        KVizzingQuestion.model_validate(ex)

    def test_media_on_discussion_entry(self):
        """A hint message can have a media attachment (e.g. an image clue)."""
        ex = load_example(0)
        ex["discussion"][1]["media"] = [
            {"type": "image", "url": None, "filename": "hint.jpg", "caption": "Here's a clue"}
        ]
        KVizzingQuestion.model_validate(ex)

    def test_null_media_on_discussion_entry_allowed(self):
        ex = load_example(0)
        for entry in ex["discussion"]:
            entry["media"] = None
        KVizzingQuestion.model_validate(ex)

    def test_has_media_false_media_null(self):
        """Standard text question: has_media=False, media=None."""
        ex = load_example(0)
        assert ex["question"]["has_media"] is False
        assert ex["question"].get("media") is None
        KVizzingQuestion.model_validate(ex)

    def test_multiple_attachments_allowed(self):
        """A message can have more than one attachment."""
        ex = self._base()
        ex["question"]["media"] = [
            {"type": "image", "filename": "a.jpg"},
            {"type": "image", "filename": "b.jpg"},
        ]
        KVizzingQuestion.model_validate(ex)


if __name__ == "__main__":
    import sys
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v"]))

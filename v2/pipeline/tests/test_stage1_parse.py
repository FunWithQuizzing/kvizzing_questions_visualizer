"""Tests for Stage 1 — Parse."""

import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.stage1_parse import run

BASE_CONFIG = {
    "source_timezone": "America/Chicago",
    "stage1": {"locale_formats": ["%m/%d/%y, %H:%M:%S", "%m/%d/%y, %I:%M:%S %p", "%d/%m/%Y, %H:%M:%S"]},
}


def _lines(fixture_name: str) -> list[str]:
    return (FIXTURES / fixture_name).read_text(encoding="utf-8").splitlines(keepends=True)


class TestStage1Parse:
    def test_us_locale_parses_correctly(self):
        msgs = run(_lines("chat_us_locale.txt"), BASE_CONFIG)
        assert len(msgs) == 5
        assert msgs[0]["username"] == "Pavan Pamidimarri"
        assert "Inaugural question" in msgs[0]["text"]

    def test_timestamps_are_utc(self):
        msgs = run(_lines("chat_us_locale.txt"), BASE_CONFIG)
        for m in msgs:
            assert m["timestamp"].endswith("Z"), f"Not UTC: {m['timestamp']}"

    def test_utc_conversion_chicago(self):
        """9/23/25 14:25:40 CDT (UTC-5) → 19:25:40 UTC."""
        msgs = run(_lines("chat_us_locale.txt"), BASE_CONFIG)
        # 2025-09-23 is CDT (UTC-5)
        assert msgs[0]["timestamp"] == "2025-09-23T19:25:40Z", msgs[0]["timestamp"]

    def test_tilde_stripped_from_username(self):
        msgs = run(_lines("chat_us_locale.txt"), BASE_CONFIG)
        for m in msgs:
            assert not m["username"].startswith("~"), f"~ not stripped: {m['username']}"

    def test_system_messages_filtered(self):
        msgs = run(_lines("chat_system_messages.txt"), BASE_CONFIG)
        # Only real user messages should remain
        usernames = {m["username"] for m in msgs}
        assert "Hum Kvizzy Se Kam Nhi || Quizzing" not in usernames

    def test_deleted_message_filtered(self):
        msgs = run(_lines("chat_system_messages.txt"), BASE_CONFIG)
        texts = [m["text"] for m in msgs]
        assert "This message was deleted" not in texts

    def test_multiline_message_joined(self):
        msgs = run(_lines("chat_multiline.txt"), BASE_CONFIG)
        # First message spans 3 lines
        assert "spans multiple lines" in msgs[0]["text"]
        assert "very detailed indeed" in msgs[0]["text"]

    def test_media_placeholder_detected(self):
        msgs = run(_lines("chat_media.txt"), BASE_CONFIG)
        q_msg = msgs[0]
        assert q_msg["has_media"] is True

    def test_media_placeholder_stripped_from_text(self):
        msgs = run(_lines("chat_media.txt"), BASE_CONFIG)
        assert "<image omitted>" not in msgs[0]["text"]

    def test_non_media_message_has_media_false(self):
        msgs = run(_lines("chat_us_locale.txt"), BASE_CONFIG)
        for m in msgs:
            assert m["has_media"] is False

    def test_24hr_locale_parsed(self):
        """3/16/26, 13:18:47 CDT (UTC-5) → 18:18:47 UTC."""
        msgs = run(_lines("chat_media.txt"), BASE_CONFIG)
        # 2026-03-16 is CDT (UTC-5)
        assert msgs[0]["timestamp"] == "2026-03-16T18:18:47Z", msgs[0]["timestamp"]

    def test_username_alias_applied(self):
        aliases = {"Pavan Pamidimarri": "pavan"}
        msgs = run(_lines("chat_us_locale.txt"), BASE_CONFIG, aliases=aliases)
        assert msgs[0]["username"] == "pavan"

    def test_question_containing_left_or_added_not_filtered(self):
        """'left' and 'added' in question text must not trigger system message filter."""
        lines = [
            "[9/23/25, 14:00:00] Pavan: She left her keys on the left side. Who added this rule?\n",
            "[9/23/25, 14:01:00] Akshay: Answer A?\n",
            "[9/23/25, 14:01:30] Aditi: Answer B?\n",
        ]
        msgs = run(lines, BASE_CONFIG)
        assert len(msgs) == 3
        assert "left" in msgs[0]["text"]

    def test_empty_input_returns_empty(self):
        assert run([], BASE_CONFIG) == []

    def test_output_keys_present(self):
        msgs = run(_lines("chat_us_locale.txt"), BASE_CONFIG)
        for m in msgs:
            assert set(m.keys()) == {"timestamp", "username", "text", "has_media"}

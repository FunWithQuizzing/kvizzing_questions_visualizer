"""Tests for Stage 0 — Date Filter."""

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

BASE_CONFIG = {
    "source_timezone": "America/Chicago",
    "chat_file": str(FIXTURES / "chat_midnight_span.txt"),
    "stage0": {"lookahead_hours": 4},
    "stage1": {"locale_formats": ["%m/%d/%y, %I:%M:%S %p", "%d/%m/%Y, %H:%M:%S"]},
}

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from stages.stage0_filter import run, _parse_line_date


class TestParsLineDate:
    def test_us_locale_date(self):
        line = "[9/23/25, 14:25:40] User: Hello"
        assert _parse_line_date(line) == date(2025, 9, 23)

    def test_us_locale_with_ltr_mark(self):
        line = "\u200e[9/23/25, 14:25:40] User: Hello"
        assert _parse_line_date(line) == date(2025, 9, 23)

    def test_intl_locale_date(self):
        line = "[23/09/2025, 14:25:40] User: Hello"
        assert _parse_line_date(line) == date(2025, 9, 23)

    def test_non_message_line(self):
        assert _parse_line_date("continuation text") is None

    def test_empty_line(self):
        assert _parse_line_date("") is None


class TestStage0Filter:
    def _make_db(self, stored_dates: list[str] = None) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE questions (id TEXT PRIMARY KEY, date TEXT NOT NULL, "
            "asker TEXT NOT NULL, solver TEXT, session_id TEXT, topic TEXT, "
            "difficulty TEXT, extraction_confidence TEXT NOT NULL, "
            "has_media INTEGER DEFAULT 0, has_reactions INTEGER DEFAULT 0, "
            "payload TEXT NOT NULL)"
        )
        if stored_dates:
            for d in stored_dates:
                conn.execute(
                    "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (d, d, "user", None, None, None, None, "high", 0, 0, "{}"),
                )
        conn.commit()
        return conn

    def test_backfill_returns_all_lines_when_db_empty(self):
        config = {**BASE_CONFIG, "chat_file": str(FIXTURES / "chat_us_locale.txt")}
        conn = self._make_db()
        lines = run(config, conn, mode="backfill")
        assert len(lines) > 0
        # All lines from the fixture should be returned
        assert any("Pavan Pamidimarri" in l for l in lines)

    def test_backfill_skips_already_stored_dates(self):
        config = {**BASE_CONFIG, "chat_file": str(FIXTURES / "chat_us_locale.txt")}
        # Mark 2025-09-23 as already stored
        conn = self._make_db(stored_dates=["2025-09-23"])
        lines = run(config, conn, mode="backfill")
        # All dates in the fixture are 2025-09-23, so nothing should be returned
        # (the lookahead adds the next day but fixture has no messages there)
        assert lines == []

    def test_incremental_returns_only_new_dates(self):
        config = {**BASE_CONFIG, "chat_file": str(FIXTURES / "chat_midnight_span.txt")}
        # last stored is 2025-09-22 — both 9/23 and 9/24 are new
        conn = self._make_db(stored_dates=["2025-09-22"])
        # Store a question on 2025-09-22 so MAX(date) is known
        conn.execute(
            "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("2025-09-22-120000", "2025-09-22", "user", None, None, None, None, "high", 0, 0, "{}"),
        )
        conn.commit()
        lines = run(config, conn, mode="incremental")
        assert len(lines) > 0

    def test_lookahead_includes_next_day_messages(self):
        """Midnight-spanning fixture: question on 9/23 night, answer on 9/24 morning."""
        config = {**BASE_CONFIG, "chat_file": str(FIXTURES / "chat_midnight_span.txt")}
        conn = self._make_db()  # empty — full backfill
        lines = run(config, conn, mode="backfill")
        # Should include both the 9/23 question and the 9/24 answer
        full = "".join(lines)
        assert "Who invented the telephone" in full
        assert "Alexander Graham Bell" in full

    def test_no_new_dates_returns_empty(self):
        config = {**BASE_CONFIG, "chat_file": str(FIXTURES / "chat_us_locale.txt")}
        conn = self._make_db(stored_dates=["2025-09-23", "2025-09-24"])
        lines = run(config, conn, mode="backfill")
        assert lines == []

    def test_none_db_conn_does_full_backfill(self):
        config = {**BASE_CONFIG, "chat_file": str(FIXTURES / "chat_us_locale.txt")}
        lines = run(config, db_conn=None, mode="backfill")
        assert len(lines) > 0

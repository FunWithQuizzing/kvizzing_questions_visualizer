"""
Stage 0 — Date Filter

Reads the raw chat file and returns a slice of lines covering the dates
that need processing, plus a lookahead buffer into the following day(s).

Inputs:
  - config: pipeline_config dict
  - db_conn: sqlite3 connection (or None for fresh backfill)
  - mode: "backfill" | "incremental"

Output:
  - List of raw text lines to pass to Stage 1
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


# WhatsApp line prefixes that carry a date we can parse cheaply
# Match both [M/D/YY, ...] and [DD/MM/YYYY, ...]
import re

_DATE_PREFIX = re.compile(
    r"^\u200e?\[(\d{1,2})/(\d{1,2})/(\d{2,4}),"
)


def _parse_line_date(line: str) -> Optional[date]:
    """Extract the calendar date from a WhatsApp message line, or None."""
    m = _DATE_PREFIX.match(line)
    if not m:
        return None
    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
    year = (2000 + c) if c < 100 else c
    # Disambiguate M/D/YY vs DD/MM/YYYY by range
    # If a > 12 it must be DD/MM; if b > 12 it must be M/D
    if b > 12:
        # b > 12 is impossible for a month, so b must be the day → format is M/D (US)
        month, day = a, b
    elif a > 12:
        month, day = b, a
    else:
        # Ambiguous — assume M/D (US locale, matches v1 export)
        month, day = a, b
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _dates_in_store(db_conn: sqlite3.Connection) -> set[date]:
    """Return the set of dates already stored in questions.db."""
    try:
        rows = db_conn.execute("SELECT DISTINCT date FROM questions").fetchall()
        return {date.fromisoformat(r[0]) for r in rows}
    except sqlite3.OperationalError:
        # Table doesn't exist yet (fresh DB before Stage 5 has run)
        return set()


def run(
    config: dict,
    db_conn: Optional[sqlite3.Connection],
    mode: str = "backfill",
    extraction_output_dir: Optional[Path] = None,
) -> list[str]:
    """
    Return the filtered list of raw chat lines to process.

    Args:
        config: parsed pipeline_config.json
        db_conn: open sqlite3 connection, or None (implies full backfill)
        mode: "backfill" or "incremental"
        extraction_output_dir: path to extraction_output/ dir (for detecting missing files)

    Returns:
        List of raw text lines (including continuation lines) covering the
        target dates plus the lookahead buffer.
    """
    chat_path = Path(config["chat_file"])
    lookahead_hours = config["stage0"]["lookahead_hours"]
    # Convert hours to a day count (ceiling) for the buffer window
    lookahead_days = (lookahead_hours + 23) // 24  # e.g. 4h → 1 extra day

    # ── 1. Read all lines ──────────────────────────────────────────────────────
    raw_lines = chat_path.read_text(encoding="utf-8").splitlines(keepends=True)

    # ── 2. Determine target dates ─────────────────────────────────────────────
    if db_conn is None or mode == "backfill":
        stored = _dates_in_store(db_conn) if db_conn is not None else set()
        # Collect every date present in the file that isn't already stored
        file_dates: set[date] = set()
        for line in raw_lines:
            d = _parse_line_date(line)
            if d:
                file_dates.add(d)
        target_dates = file_dates - stored

        # Also include dates that are in DB but missing their extraction_output
        # file, so the pipeline can regenerate it (needed for DB rebuilds).
        if extraction_output_dir and extraction_output_dir.is_dir():
            for d in stored:
                ext_file = extraction_output_dir / f"{d.isoformat()}.json"
                if not ext_file.exists() and d in file_dates:
                    target_dates.add(d)
    else:
        # Incremental: dates strictly after last_stored_date
        try:
            rows = db_conn.execute("SELECT MAX(date) FROM questions").fetchone()
            last_stored = date.fromisoformat(rows[0]) if rows[0] else None
        except sqlite3.OperationalError:
            last_stored = None
        if last_stored is None:
            # No data yet — fall back to full backfill
            return run(config, db_conn, mode="backfill")
        file_dates = set()
        for line in raw_lines:
            d = _parse_line_date(line)
            if d and d > last_stored:
                file_dates.add(d)
        target_dates = file_dates

    if not target_dates:
        return []

    # ── 3. Expand with lookahead buffer ───────────────────────────────────────
    # For each target date, also include the next `lookahead_days` days so that
    # Q&A threads started late at night are captured in full.
    expanded: set[date] = set(target_dates)
    for d in list(target_dates):
        for i in range(1, lookahead_days + 1):
            expanded.add(d + timedelta(days=i))

    # ── 4. Filter lines ───────────────────────────────────────────────────────
    result: list[str] = []
    current_in_window = False

    for line in raw_lines:
        d = _parse_line_date(line)
        if d is not None:
            current_in_window = d in expanded
        if current_in_window:
            result.append(line)

    return result

"""
Re-enrich all questions that have fewer than 2 topics.

Reads every question from questions.db, runs Stage 4 on those with 0 or 1 topic,
writes enriched rows back to questions.db, then re-exports all JSON files.

Usage:
    cd v2/pipeline
    python3 reenrich_topics.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).parent
_V2_DIR = _PIPELINE_DIR.parent

sys.path.insert(0, str(_PIPELINE_DIR))
sys.path.insert(0, str(_V2_DIR / "schema"))

from utils.logging import setup as _setup_logging

log = _setup_logging(_PIPELINE_DIR / "logs")

from clients.llm import get_client
from utils.config import load_config
from schema import KVizzingQuestion
from stages.stage4_enrich import enrich
from stages.stage5_store import _to_row, _INSERT_SQL, _FTS_INSERT_SQL, init_db
from stages.stage6_export import run as stage6


def _load_all_questions(conn: sqlite3.Connection) -> list[KVizzingQuestion]:
    rows = conn.execute("SELECT payload FROM questions").fetchall()
    questions = []
    for (payload,) in rows:
        try:
            questions.append(KVizzingQuestion.model_validate_json(payload))
        except Exception as e:
            log.warning("Skipping malformed row: %s", e)
    return questions


def _upsert_questions(conn: sqlite3.Connection, questions: list[KVizzingQuestion]) -> None:
    """Upsert enriched questions back into the DB (payload + topic column)."""
    # Rebuild FTS: delete existing entries for these ids, then re-insert
    ids = [q.id for q in questions]
    placeholders = ",".join("?" * len(ids))

    with conn:
        conn.executemany(_INSERT_SQL, [_to_row(q) for q in questions])

        # Sync FTS table
        conn.execute(f"DELETE FROM questions_fts WHERE id IN ({placeholders})", ids)
        fts_rows = []
        for q in questions:
            rowid = conn.execute(
                "SELECT rowid FROM questions WHERE id = ?", (q.id,)
            ).fetchone()
            if rowid:
                fts_rows.append((
                    rowid[0],
                    q.id,
                    q.question.text,
                    q.answer.text if q.answer else "",
                    " ".join(q.question.tags or []),
                ))
        conn.executemany(_FTS_INSERT_SQL, fts_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-enrich topics for all questions with < 2 topics")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing anything")
    args = parser.parse_args()

    config = load_config(_PIPELINE_DIR / "config")

    db_path = _V2_DIR / "data" / "questions.db"
    output_dir = _V2_DIR / "visualizer" / "static" / "data"
    members_config = _PIPELINE_DIR / "config" / "members.json"
    session_overrides_config = _PIPELINE_DIR / "config" / "session_overrides.json"
    state_path = _V2_DIR / "data" / "pipeline_state.json"

    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    log.info("Loading all questions from DB…")
    all_questions = _load_all_questions(conn)
    log.info("  Total: %d questions", len(all_questions))

    needs_enrich = [q for q in all_questions if len(q.question.topics) < 2]
    log.info("  Need (re-)enrichment (< 2 topics): %d", len(needs_enrich))

    if args.dry_run:
        log.info("Dry run — exiting without changes.")
        conn.close()
        return

    client = get_client()
    if client is None:
        log.error("No LLM client available. Set ANTHROPIC_API_KEY or GOOGLE_API_KEY.")
        conn.close()
        sys.exit(1)

    log.info("Running Stage 4 enrichment…")
    enriched = enrich(needs_enrich, config, client)

    gained_secondary = sum(1 for q in enriched if len(q.question.topics) >= 2)
    log.info("  %d questions now have 2 topics", gained_secondary)
    log.info("  %d questions still have < 2 topics (LLM found no meaningful secondary)", len(enriched) - gained_secondary)

    log.info("Writing enriched questions back to DB…")
    _upsert_questions(conn, enriched)

    log.info("Re-exporting JSON files…")
    counts = stage6(
        conn,
        output_dir,
        members_config_path=members_config,
        session_overrides_path=session_overrides_config,
        state_path=state_path,
    )
    for k, v in counts.items():
        log.info("  %s: %s", k, f"{v:,}")

    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()

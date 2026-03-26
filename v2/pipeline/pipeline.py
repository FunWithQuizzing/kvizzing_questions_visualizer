"""
KVizzing v2 Pipeline CLI

Run from v2/pipeline/:

  python3 pipeline.py backfill          # process all dates not yet in the store
  python3 pipeline.py incremental       # process only dates after last_stored_date
  python3 pipeline.py export            # re-export JSON from questions.db (no LLM)
  python3 pipeline.py enrich-reactions --db PATH/TO/ChatStorage.sqlite
  python3 pipeline.py enrich-media     --media-dir PATH/TO/WhatsApp/Media

All file paths in pipeline_config.json are resolved relative to v2/ (the parent
of this script's directory).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date as Date, timedelta
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────

# v2/pipeline/pipeline.py → V2_DIR = v2/
_PIPELINE_DIR = Path(__file__).parent
V2_DIR = _PIPELINE_DIR.parent

sys.path.insert(0, str(_PIPELINE_DIR))
sys.path.insert(0, str(V2_DIR / "schema"))

from stages.stage0_filter import run as stage0
from stages.stage1_parse import run as stage1
from stages.stage2_extract import run as stage2
from stages.stage3_structure import run as stage3
from stages.stage4_enrich import run as stage4
from stages.stage5_store import run as stage5
from stages.stage6_export import run as stage6


# ── Config + state ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    path = _PIPELINE_DIR / "config" / "pipeline_config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_aliases() -> dict:
    path = _PIPELINE_DIR / "config" / "username_aliases.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _llm_client():
    """Return an Anthropic client, or None if the package isn't installed."""
    try:
        import anthropic
        return anthropic.Anthropic()
    except ImportError:
        return None


# ── Shared pipeline run ───────────────────────────────────────────────────────

def _run_pipeline(mode: str) -> None:
    config = _load_config()
    # Resolve chat_file relative to V2_DIR (config paths are V2-relative)
    config = dict(config)
    config["chat_file"] = str(V2_DIR / config["chat_file"])
    aliases = _load_aliases()

    data_dir = V2_DIR / "data"
    db_path = data_dir / "questions.db"
    errors_dir = data_dir / "errors"
    state_path = data_dir / "pipeline_state.json"
    members_config = _PIPELINE_DIR / "config" / "members.json"

    data_dir.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(str(db_path))
    client = _llm_client()
    if client is None:
        print("WARNING: anthropic package not found — running without LLM extraction.")

    try:
        # ── Stage 0 — Filter ─────────────────────────────────────────────────
        print(f"[Stage 0] Filtering lines ({mode})…")
        lines = stage0(config, db, mode=mode)
        if not lines:
            print("  No new dates to process.")
            print("[Stage 6] Exporting JSON files…")
            counts = stage6(db, data_dir, members_config_path=members_config, state_path=state_path)
            _print_counts(counts)
            return
        print(f"  {len(lines):,} lines in window.")

        # ── Stage 1 — Parse ───────────────────────────────────────────────────
        print("[Stage 1] Parsing messages…")
        messages = stage1(lines, config, aliases=aliases)
        print(f"  {len(messages):,} messages parsed.")

        # Group messages by UTC date so we can process and store date-by-date.
        # For each date D we include the next day's messages too, covering the
        # 4-hour lookahead buffer (late-night Q&A threads that span midnight).
        by_date: dict[str, list[dict]] = defaultdict(list)
        for m in messages:
            by_date[m["timestamp"][:10]].append(m)

        target_dates = sorted(by_date.keys())
        print(f"  {len(target_dates)} dates in window.")

        total_stored = 0

        for date_str in target_dates:
            # Build window: this date + next day (lookahead)
            next_day = str(
                Date(int(date_str[:4]), int(date_str[5:7]), int(date_str[8:]))
                + timedelta(days=1)
            )
            window = by_date.get(date_str, []) + by_date.get(next_day, [])

            # ── Stage 2 — Extract ─────────────────────────────────────────
            candidates = stage2(window, config, llm_client=client)
            if not candidates:
                print(f"  [{date_str}] 0 candidates.")
                continue

            # ── Stage 3 — Structure ───────────────────────────────────────
            questions = stage3(candidates, config, errors_dir=errors_dir)

            # Keep only questions dated on this specific date to avoid
            # double-storing questions that appear in multiple windows.
            questions = [q for q in questions if str(q.date) == date_str]
            if not questions:
                continue

            # ── Stage 4 — Enrich ──────────────────────────────────────────
            questions = stage4(questions, config, llm_client=client)

            # ── Stage 5 — Store (commits immediately) ─────────────────────
            count = stage5(questions, db, state_path=state_path)
            total_stored += count
            print(f"  [{date_str}] {count} questions stored  (running total: {total_stored})")

        print(f"\n[Stage 5] Done — {total_stored:,} questions stored.")

        # ── Stage 6 — Export ──────────────────────────────────────────────────
        print("[Stage 6] Exporting JSON files…")
        counts = stage6(db, data_dir, members_config_path=members_config, state_path=state_path)
        _print_counts(counts)

    finally:
        db.close()


def _print_counts(counts: dict) -> None:
    for key, val in counts.items():
        print(f"  {key}: {val:,}")


# ── Export-only ───────────────────────────────────────────────────────────────

def _run_export() -> None:
    config = _load_config()
    data_dir = V2_DIR / "data"
    db_path = data_dir / "questions.db"
    state_path = data_dir / "pipeline_state.json"
    members_config = _PIPELINE_DIR / "config" / "members.json"

    if not db_path.exists():
        print(f"ERROR: {db_path} not found. Run backfill first.")
        sys.exit(1)

    db = sqlite3.connect(str(db_path))
    try:
        print("[Stage 6] Exporting JSON files…")
        counts = stage6(db, data_dir, members_config_path=members_config, state_path=state_path)
        _print_counts(counts)
    finally:
        db.close()


# ── Enrichment stubs ──────────────────────────────────────────────────────────

def _run_enrich_reactions(db_path: str) -> None:
    print("enrich-reactions: not yet implemented.")
    print(f"  Source DB: {db_path}")
    sys.exit(1)


def _run_enrich_media(media_dir: str) -> None:
    print("enrich-media: not yet implemented.")
    print(f"  Media dir: {media_dir}")
    sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="KVizzing v2 pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("backfill", help="Process all dates not yet in the store")
    sub.add_parser("incremental", help="Process only new dates since last run")
    sub.add_parser("export", help="Re-export JSON files from questions.db")

    p_reactions = sub.add_parser("enrich-reactions", help="Enrich reactions from WhatsApp SQLite backup")
    p_reactions.add_argument("--db", required=True, metavar="PATH", help="Path to ChatStorage.sqlite")

    p_media = sub.add_parser("enrich-media", help="Match media files from WhatsApp backup")
    p_media.add_argument("--media-dir", required=True, metavar="PATH", help="Path to WhatsApp Media directory")

    args = parser.parse_args()

    if args.command in ("backfill", "incremental"):
        _run_pipeline(args.command)
    elif args.command == "export":
        _run_export()
    elif args.command == "enrich-reactions":
        _run_enrich_reactions(args.db)
    elif args.command == "enrich-media":
        _run_enrich_media(args.media_dir)


if __name__ == "__main__":
    main()

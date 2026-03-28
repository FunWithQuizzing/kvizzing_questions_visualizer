"""
KVizzing v2 Pipeline CLI

Run from v2/pipeline/:

  python3 pipeline.py backfill          # process all dates not yet in the store
  python3 pipeline.py incremental       # process only dates after last_stored_date
  python3 pipeline.py export            # re-export JSON from questions.db (no LLM)
  python3 pipeline.py generate-images   # generate background images for new sessions
  python3 pipeline.py enrich-reactions --db PATH/TO/ChatStorage.sqlite
  python3 pipeline.py enrich-media     --media-dir PATH/TO/WhatsApp/Media

All file paths in pipeline_config.json are resolved relative to v2/ (the parent
of this script's directory). Logs are written to pipeline/logs/YYYY-MM-DD.log.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import date as Date, timedelta
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────

_PIPELINE_DIR = Path(__file__).parent
V2_DIR = _PIPELINE_DIR.parent

sys.path.insert(0, str(_PIPELINE_DIR))
sys.path.insert(0, str(V2_DIR / "schema"))

# ── Bootstrap logging before any other local imports ─────────────────────────

from utils.logging import setup as _setup_logging

log = _setup_logging(_PIPELINE_DIR / "logs")

# ── Local imports ─────────────────────────────────────────────────────────────

from clients.llm import get_client
from utils.config import load_config, load_aliases

from stages.stage0_filter import run as stage0
from stages.stage1_parse import run as stage1
from stages.stage2_extract import run as stage2
from stages.stage3_structure import run as stage3
from stages.stage4_enrich import run as stage4
from stages.stage5_store import run as stage5
from stages.stage6_export import run as stage6
from generate_session_images import main as _generate_images_main
from preserve_topics import main as _preserve_topics


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_counts(counts: dict) -> None:
    for key, val in counts.items():
        log.info("  %s: %s", key, f"{val:,}")


# ── Pipeline run ──────────────────────────────────────────────────────────────

def _run_pipeline(mode: str) -> None:
    config = load_config(_PIPELINE_DIR / "config")
    config = dict(config)
    config["chat_file"] = str(V2_DIR / config["chat_file"])
    aliases = load_aliases(_PIPELINE_DIR / "config")

    data_dir = V2_DIR / "data"
    output_dir = V2_DIR / "visualizer" / "static" / "data"
    db_path = data_dir / "questions.db"
    errors_dir = data_dir / "errors"
    state_path = data_dir / "pipeline_state.json"
    members_config = _PIPELINE_DIR / "config" / "members.json"
    session_overrides_config = _PIPELINE_DIR / "config" / "session_overrides.json"
    extraction_output_dir = data_dir / "extraction_output"

    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = get_client()
    if client is None:
        log.warning("No LLM client — running without extraction.")

    log.info("=" * 60)
    log.info("Pipeline run  mode=%s", mode)
    log.info("=" * 60)

    db = sqlite3.connect(str(db_path))
    try:
        # Stage 0 — Filter
        log.info("[Stage 0] Filtering lines (%s)…", mode)
        lines = stage0(config, db, mode=mode)
        if not lines:
            log.info("  No new dates to process.")
            log.info("[Stage 6] Exporting JSON files…")
            counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
            _log_counts(counts)
            return
        log.info("  %s lines in window.", f"{len(lines):,}")

        # Stage 1 — Parse
        log.info("[Stage 1] Parsing messages…")
        messages = stage1(lines, config, aliases=aliases)
        log.info("  %s messages parsed.", f"{len(messages):,}")

        by_date: dict[str, list[dict]] = defaultdict(list)
        for m in messages:
            by_date[m["timestamp"][:10]].append(m)

        target_dates = sorted(by_date.keys())
        log.info("  %d dates in window.", len(target_dates))

        total_stored = 0

        import json as _json
        for date_str in target_dates:
            # If a manually-verified extraction file exists for this date,
            # use it instead of running LLM extraction (stage 2). This ensures
            # manual corrections survive DB rebuilds.
            extraction_file = extraction_output_dir / f"{date_str}.json"
            if extraction_file.exists():
                try:
                    candidates = _json.loads(extraction_file.read_text(encoding="utf-8"))
                    if not candidates:
                        log.info("  [%s] extraction_output file empty — skipping.", date_str)
                        continue
                    log.info("  [%s] Using extraction_output file (%d entries, skipping LLM).", date_str, len(candidates))
                except (OSError, _json.JSONDecodeError) as e:
                    log.warning("  [%s] Failed to read extraction_output file: %s — falling back to LLM.", date_str, e)
                    candidates = None
            else:
                candidates = None

            if candidates is None:
                next_day = str(
                    Date(int(date_str[:4]), int(date_str[5:7]), int(date_str[8:]))
                    + timedelta(days=1)
                )
                window = by_date.get(date_str, []) + by_date.get(next_day, [])
                # Stage 2 — Extract
                log.debug("  [%s] Stage 2: extracting from %d messages…", date_str, len(window))
                candidates = stage2(window, config, llm_client=client)
                if not candidates:
                    log.info("  [%s] 0 candidates.", date_str)
                    continue

            # Stage 3 — Structure
            questions = stage3(candidates, config, errors_dir=errors_dir)
            questions = [q for q in questions if str(q.date) == date_str]
            if not questions:
                log.debug("  [%s] 0 valid questions after date filter.", date_str)
                continue
            log.debug("  [%s] %d questions structured.", date_str, len(questions))

            # Stage 4 — Enrich
            questions = stage4(questions, config, llm_client=client)

            # Write enriched topics/tags back to extraction_output file so they
            # survive future DB rebuilds. Keyed by question_timestamp.
            if extraction_file.exists():
                try:
                    raw_entries = _json.loads(extraction_file.read_text(encoding="utf-8"))
                    enriched_by_ts = {
                        q.question.timestamp: q for q in questions
                        if q.question.timestamp
                    }
                    updated = False
                    for entry in raw_entries:
                        ts = entry.get("question_timestamp")
                        q = enriched_by_ts.get(ts)
                        if q and q.question.topic and not entry.get("topic"):
                            entry["topic"] = q.question.topic.value
                            entry["tags"] = q.question.tags or []
                            updated = True
                    if updated:
                        extraction_file.write_text(
                            _json.dumps(raw_entries, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        log.debug("  [%s] Wrote enriched topics/tags back to extraction_output file.", date_str)
                except Exception as e:
                    log.warning("  [%s] Could not write back enrichment to extraction_output: %s", date_str, e)

            # Stage 5 — Store
            count = stage5(questions, db, state_path=state_path)
            total_stored += count
            log.info("  [%s] %d questions stored  (running total: %d)", date_str, count, total_stored)

        log.info("")
        log.info("[Stage 5] Done — %s questions stored.", f"{total_stored:,}")

        # Stage 6 — Export
        log.info("[Stage 6] Exporting JSON files…")
        counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
        _log_counts(counts)

        # Preserve manually-curated topics (converts singular topic → topics[])
        log.info("[Post-export] Preserving topic overrides…")
        _preserve_topics()

    except Exception:
        log.exception("Pipeline crashed.")
        raise
    finally:
        db.close()
        log.info("Pipeline run complete.")


# ── Export-only ───────────────────────────────────────────────────────────────

def _run_export() -> None:
    config = load_config(_PIPELINE_DIR / "config")
    data_dir = V2_DIR / "data"
    output_dir = V2_DIR / "visualizer" / "static" / "data"
    db_path = data_dir / "questions.db"
    state_path = data_dir / "pipeline_state.json"
    members_config = _PIPELINE_DIR / "config" / "members.json"
    session_overrides_config = _PIPELINE_DIR / "config" / "session_overrides.json"

    if not db_path.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))
    try:
        log.info("[Stage 6] Exporting JSON files…")
        counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
        _log_counts(counts)
        log.info("[Post-export] Preserving topic overrides…")
        _preserve_topics()
        log.info("Export complete.")
    except Exception:
        log.exception("Export crashed.")
        raise
    finally:
        db.close()


# ── Enrichment stubs ──────────────────────────────────────────────────────────

def _run_generate_images() -> None:
    log.info("[generate-images] Generating session background images…")
    _generate_images_main()
    log.info("[generate-images] Done.")


def _run_enrich_reactions(db_path: str) -> None:
    log.error("enrich-reactions: not yet implemented.  Source DB: %s", db_path)
    sys.exit(1)


def _run_enrich_media(media_dir: str) -> None:
    log.error("enrich-media: not yet implemented.  Media dir: %s", media_dir)
    sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="KVizzing v2 pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("backfill",    help="Process all dates not yet in the store")
    sub.add_parser("incremental", help="Process only new dates since last run")
    sub.add_parser("export",      help="Re-export JSON files from questions.db")
    sub.add_parser("generate-images", help="Generate background images for new sessions (via Stable Horde)")

    p_reactions = sub.add_parser("enrich-reactions", help="Enrich reactions from WhatsApp SQLite backup")
    p_reactions.add_argument("--db", required=True, metavar="PATH", help="Path to ChatStorage.sqlite")

    p_media = sub.add_parser("enrich-media", help="Match media files from WhatsApp backup")
    p_media.add_argument("--media-dir", required=True, metavar="PATH", help="Path to WhatsApp Media directory")

    args = parser.parse_args()

    if args.command in ("backfill", "incremental"):
        _run_pipeline(args.command)
    elif args.command == "export":
        _run_export()
    elif args.command == "generate-images":
        _run_generate_images()
    elif args.command == "enrich-reactions":
        _run_enrich_reactions(args.db)
    elif args.command == "enrich-media":
        _run_enrich_media(args.media_dir)


if __name__ == "__main__":
    main()

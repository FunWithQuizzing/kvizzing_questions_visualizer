"""
KVizzing v2 Pipeline CLI

Run from v2/pipeline/:

  python3 pipeline.py backfill          # process all dates not yet in the store
  python3 pipeline.py incremental       # process only dates after last_stored_date
  python3 pipeline.py export            # re-export JSON from questions.db (no LLM)
  python3 pipeline.py generate-images   # generate background images for new sessions
  python3 pipeline.py enrich-reactions --db PATH/TO/ChatStorage.sqlite
  python3 pipeline.py enrich-media     --media-dir PATH/TO/WhatsApp/Media
  python3 pipeline.py reenrich         [--dry-run]  # re-run LLM enrichment on questions with < 2 topics
  python3 pipeline.py normalize-tags   [--dry-run]  # strip format tags, fix near-duplicates in DB
  python3 pipeline.py assign-topics    [--dry-run]  # assign topics via rules (no LLM)

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
from stages.stage4_enrich import enrich as _stage4_enrich, _normalize_tags
from stages.stage5_store import load_all as _load_all, upsert as _upsert
from utils.topic_rules import assign_topics as _assign_topics
from utils.generate_session_images import main as _generate_images_main


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
                candidates = stage2(window, config, llm_client=client, date_str=date_str)
                if not candidates:
                    log.info("  [%s] 0 candidates.", date_str)
                    continue
                    
                # Save successfully audited extraction back to disk
                try:
                    extraction_file.parent.mkdir(parents=True, exist_ok=True)
                    extraction_file.write_text(
                        _json.dumps(candidates, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )
                    log.debug("  [%s] Saved %d candidates to %s", date_str, len(candidates), extraction_file.name)
                except Exception as e:
                    log.warning("  [%s] Could not save extraction to file: %s", date_str, e)

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
                        if q and q.question.topics and not entry.get("topics"):
                            entry["topics"] = [t.value for t in q.question.topics]
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
        log.info("Export complete.")
    except Exception:
        log.exception("Export crashed.")
        raise
    finally:
        db.close()


# ── Post-hoc subcommands ──────────────────────────────────────────────────────

def _post_hoc_paths():
    data_dir = V2_DIR / "data"
    return {
        "db_path": data_dir / "questions.db",
        "output_dir": V2_DIR / "visualizer" / "static" / "data",
        "members_config": _PIPELINE_DIR / "config" / "members.json",
        "session_overrides_config": _PIPELINE_DIR / "config" / "session_overrides.json",
        "state_path": data_dir / "pipeline_state.json",
    }


def _run_reenrich(dry_run: bool) -> None:
    """Re-enrich questions that have fewer than 2 topics via LLM (Stage 4)."""
    config = load_config(_PIPELINE_DIR / "config")
    paths = _post_hoc_paths()
    db_path = paths["db_path"]
    if not db_path.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        log.info("Loading all questions from DB…")
        all_questions = _load_all(conn)
        log.info("  Total: %d questions", len(all_questions))
        needs = [q for q in all_questions if len(q.question.topics) < 2]
        log.info("  Need (re-)enrichment (< 2 topics): %d", len(needs))

        if dry_run:
            log.info("Dry run — exiting without changes.")
            return

        client = get_client()
        if client is None:
            log.error("No LLM client available. Set USE_OLLAMA=1, GROQ_API_KEY, or ANTHROPIC_API_KEY.")
            sys.exit(1)

        log.info("Running Stage 4 enrichment…")
        enriched = _stage4_enrich(needs, config, client)
        gained = sum(1 for q in enriched if len(q.question.topics) >= 2)
        log.info("  %d questions now have 2 topics", gained)
        log.info("  %d still have < 2 topics", len(enriched) - gained)

        log.info("Writing enriched questions to DB…")
        _upsert(enriched, conn)
        log.info("Re-exporting JSON files…")
        counts = stage6(conn, paths["output_dir"], members_config_path=paths["members_config"],
                        session_overrides_path=paths["session_overrides_config"], state_path=paths["state_path"])
        _log_counts(counts)
    finally:
        conn.close()
    log.info("reenrich complete.")


def _run_normalize_tags(dry_run: bool) -> None:
    """Normalize tags in the DB: strip format tags, rename near-duplicates."""
    paths = _post_hoc_paths()
    db_path = paths["db_path"]
    if not db_path.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        log.info("Loading all questions from DB…")
        all_questions = _load_all(conn)
        log.info("  Total: %d questions", len(all_questions))

        changed = []
        for q in all_questions:
            old_tags = q.question.tags or []
            new_tags = _normalize_tags(old_tags)
            if new_tags != old_tags:
                changed.append(q.model_copy(update={
                    "question": q.question.model_copy(update={"tags": new_tags})
                }))
        log.info("  %d questions have tags to normalize", len(changed))

        if dry_run:
            log.info("Dry run — sample changes:")
            for q in changed[:10]:
                log.info("  [%s] %s → %s", q.id, (q.question.tags or []), _normalize_tags(q.question.tags or []))
            return

        if changed:
            log.info("Writing normalized tags to DB…")
            _upsert(changed, conn)
            log.info("Re-exporting JSON files…")
            counts = stage6(conn, paths["output_dir"], members_config_path=paths["members_config"],
                            session_overrides_path=paths["session_overrides_config"], state_path=paths["state_path"])
            _log_counts(counts)
        else:
            log.info("Nothing to normalize.")
    finally:
        conn.close()
    log.info("normalize-tags complete.")


def _run_assign_topics(dry_run: bool) -> None:
    """Assign primary + secondary topics via rule-based matching (no LLM)."""
    paths = _post_hoc_paths()
    db_path = paths["db_path"]
    if not db_path.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        log.info("Loading all questions from DB…")
        all_questions = _load_all(conn)
        log.info("  Total: %d questions", len(all_questions))

        enriched = [_assign_topics(q) for q in all_questions]

        no_topic   = sum(1 for q in enriched if not q.question.topics)
        one_topic  = sum(1 for q in enriched if len(q.question.topics) == 1)
        two_topics = sum(1 for q in enriched if len(q.question.topics) >= 2)
        log.info("  No topic:          %d", no_topic)
        log.info("  Primary only:      %d", one_topic)
        log.info("  Primary+secondary: %d", two_topics)

        if dry_run:
            log.info("Dry run — sample assignments:")
            for q in enriched[:15]:
                t = q.question.topics
                log.info("  [%s] %s | %s",
                    " + ".join(x.value for x in t) if t else "NONE",
                    (q.question.text or "")[:60],
                    q.question.tags,
                )
            return

        log.info("Writing to DB…")
        _upsert(enriched, conn)
        log.info("Re-exporting JSON files…")
        counts = stage6(conn, paths["output_dir"], members_config_path=paths["members_config"],
                        session_overrides_path=paths["session_overrides_config"], state_path=paths["state_path"])
        _log_counts(counts)
    finally:
        conn.close()
    log.info("assign-topics complete.")


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

    p_reenrich = sub.add_parser("reenrich", help="Re-enrich questions with < 2 topics via LLM (Stage 4)")
    p_reenrich.add_argument("--dry-run", action="store_true", help="Show counts without writing anything")

    p_norm = sub.add_parser("normalize-tags", help="Strip format tags and rename near-duplicates in the DB")
    p_norm.add_argument("--dry-run", action="store_true", help="Show changes without writing anything")

    p_topics = sub.add_parser("assign-topics", help="Assign primary + secondary topics via rules (no LLM)")
    p_topics.add_argument("--dry-run", action="store_true", help="Show assignments without writing anything")

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
    elif args.command == "reenrich":
        _run_reenrich(args.dry_run)
    elif args.command == "normalize-tags":
        _run_normalize_tags(args.dry_run)
    elif args.command == "assign-topics":
        _run_assign_topics(args.dry_run)


if __name__ == "__main__":
    main()

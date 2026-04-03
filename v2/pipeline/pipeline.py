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
  python3 pipeline.py export-rejected                # export rejected candidates to JSON

All file paths in pipeline_config.json are resolved relative to v2/ (the parent
of this script's directory). Logs are written to pipeline/logs/YYYY-MM-DD.log.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date as Date, timedelta
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────

_PIPELINE_DIR = Path(__file__).parent
V2_DIR = _PIPELINE_DIR.parent

sys.path.insert(0, str(_PIPELINE_DIR))
sys.path.insert(0, str(V2_DIR / "schema"))

# ── Load .env (silently ignored if missing) ───────────────────────────────────

def _load_env() -> None:
    env_path = _PIPELINE_DIR / ".env"
    if not env_path.exists():
        return
    import os
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:  # don't override vars already in environment
            os.environ[key] = value

_load_env()

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
from utils.export_rejected import export_rejected as _export_rejected


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_counts(counts: dict) -> None:
    for key, val in counts.items():
        log.info("  %s: %s", key, f"{val:,}")


def _write_rejected_candidates(
    by_date: dict[str, list[dict]],
    extraction_dir: Path,
    rejected_dir: Path,
    config: dict,
) -> None:
    """
    Write rejected-candidate .txt files for dates that have extraction files.
    Compares heuristic prefilter candidates against extracted questions to find
    candidates the LLM chose not to extract.
    """
    import json as _json
    from datetime import datetime as _dt
    from stages.stage2_extract import prefilter

    rejected_dir.mkdir(parents=True, exist_ok=True)
    # Clean old files
    for old in rejected_dir.iterdir():
        if old.suffix == ".txt":
            old.unlink()

    total_rejected = 0
    total_threads = 0
    _MIN_TEXT_LEN = 40
    _REPLY_WINDOW_S = 600
    _THREAD_GAP_S = 180

    for date_str in sorted(by_date.keys()):
        ext_file = extraction_dir / f"{date_str}.json"
        if not ext_file.exists():
            continue

        day_messages = by_date[date_str]
        candidate_indices = prefilter(day_messages, config)
        if not candidate_indices:
            continue

        extracted_timestamps: set[str] = set()
        extracted_dts: list[_dt] = []
        try:
            for entry in _json.loads(ext_file.read_text(encoding="utf-8")):
                ts = entry.get("question_timestamp", "")
                extracted_timestamps.add(ts)
                try:
                    extracted_dts.append(_dt.fromisoformat(ts.rstrip("Z")))
                except Exception:
                    pass
        except Exception:
            pass

        def _is_reply_to_extracted(ts_str: str) -> bool:
            try:
                t = _dt.fromisoformat(ts_str.rstrip("Z"))
            except Exception:
                return False
            for eq_dt in extracted_dts:
                delta = (t - eq_dt).total_seconds()
                if 0 < delta <= _REPLY_WINDOW_S:
                    return True
            return False

        good_candidates: list[tuple[int, dict]] = []
        for idx in candidate_indices:
            msg = day_messages[idx]
            msg_ts = msg["timestamp"]
            text = msg["text"].strip()
            if msg_ts in extracted_timestamps:
                continue
            if len(text) < _MIN_TEXT_LEN:
                continue
            if _is_reply_to_extracted(msg_ts):
                continue
            good_candidates.append((idx, msg))

        if not good_candidates:
            continue

        threads: list[list[tuple[int, dict]]] = []
        current_thread: list[tuple[int, dict]] = [good_candidates[0]]
        for i in range(1, len(good_candidates)):
            prev_ts = current_thread[-1][1]["timestamp"]
            curr_ts = good_candidates[i][1]["timestamp"]
            try:
                prev_dt = _dt.fromisoformat(prev_ts.rstrip("Z"))
                curr_dt = _dt.fromisoformat(curr_ts.rstrip("Z"))
                gap = (curr_dt - prev_dt).total_seconds()
            except Exception:
                gap = _THREAD_GAP_S + 1
            if gap <= _THREAD_GAP_S:
                current_thread.append(good_candidates[i])
            else:
                threads.append(current_thread)
                current_thread = [good_candidates[i]]
        threads.append(current_thread)

        extracted_count = len(extracted_timestamps)
        total_rejected += sum(len(t) for t in threads)
        total_threads += len(threads)
        out_lines = [f"# {date_str} — {len(threads)} thread(s), {sum(len(t) for t in threads)} candidate(s)\n"]
        out_lines.append(f"# (Extracted: {extracted_count} questions)\n\n")

        for ti, thread in enumerate(threads, 1):
            first_idx = thread[0][0]
            last_idx = thread[-1][0]
            ctx_start = max(0, first_idx - 8)
            ctx_end = min(len(day_messages), last_idx + 13)
            candidate_idxs = {idx for idx, _ in thread}

            out_lines.append(f"## Thread {ti}  ({len(thread)} candidate{'s' if len(thread) > 1 else ''})\n\n")
            for idx, msg in thread:
                reason = (
                    "question_mark" if msg["text"].strip().endswith("?") else
                    "question_prefix" if any(msg["text"].strip().upper().startswith(p) for p in ["Q.", "Q:", "Q ", "FLASH Q", "QUESTION"]) else
                    "media_short_text" if msg.get("has_media") else
                    "session_marker"
                )
                out_lines.append(f"  Candidate: [{msg['timestamp'][11:19]}] {msg['username']}  [{reason}]\n")
                out_lines.append(f"  Text: {msg['text'][:300]}\n\n")

            out_lines.append("Context:\n")
            for ci in range(ctx_start, ctx_end):
                m = day_messages[ci]
                prefix = ">>>" if ci in candidate_idxs else "   "
                out_lines.append(f"  {prefix} [{m['timestamp']}] {m['username']}: {m['text'][:200]}\n")
            out_lines.append("\n---\n\n")

        (rejected_dir / f"{date_str}.txt").write_text("".join(out_lines), encoding="utf-8")

    log.info("  Rejected candidates: %d candidates in %d threads", total_rejected, total_threads)


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
        skipped_dates: list[str] = []

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
                try:
                    candidates = stage2(window, config, llm_client=client, date_str=date_str)
                except RuntimeError as e:
                    log.error("  [%s] Stage 2 failed — skipping date: %s", date_str, e)
                    skipped_dates.append(date_str)
                    continue
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

                # Gemini free tier: 5 RPM for pro → wait 13s between LLM calls
                time.sleep(13)

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

        if skipped_dates:
            log.warning(
                "%d date(s) skipped due to unresolvable extraction errors: %s",
                len(skipped_dates), ", ".join(skipped_dates),
            )
            log.warning("Re-run with a different LLM or manually fix extraction_output files for these dates.")

        # Stage 6 — Export
        log.info("[Stage 6] Exporting JSON files…")
        counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
        _log_counts(counts)

        # Rejected candidates
        log.info("[Rejected] Writing rejected candidate files…")
        rejected_dir = data_dir / "rejected_candidates"
        _write_rejected_candidates(by_date, extraction_output_dir, rejected_dir, config)
        rejected_json = output_dir / "rejected_candidates.json"
        if rejected_dir.exists():
            count = _export_rejected(rejected_dir, rejected_json)
            log.info("  Exported %d rejected entries to %s", count, rejected_json.name)

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


def _run_enrich_media(media_dir: str, dry_run: bool = False) -> None:
    """Match media files to questions by timestamp, populate question.media[]."""
    from utils.media_match import match_media

    media_path = Path(media_dir)
    if not media_path.exists() or not media_path.is_dir():
        log.error("Media directory not found: %s", media_path)
        sys.exit(1)

    config = load_config(_PIPELINE_DIR / "config")
    paths = _post_hoc_paths()
    db_path_obj = paths["db_path"]
    if not db_path_obj.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path_obj)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path_obj))
    try:
        log.info("Loading all questions from DB…")
        all_questions = _load_all(conn)
        has_media = [q for q in all_questions if q.question.has_media]
        already_set = sum(1 for q in has_media if q.question.media is not None)
        log.info(
            "  Total: %d questions  |  has_media=True: %d  |  already matched: %d",
            len(all_questions), len(has_media), already_set,
        )

        enriched_has_media = match_media(has_media, media_path, config)
        newly_matched = [q for q in enriched_has_media if q.question.media is not None and
                         next((oq for oq in has_media if oq.id == q.id), None) and
                         next((oq for oq in has_media if oq.id == q.id)).question.media is None]

        if dry_run:
            log.info("Dry run — %d questions would gain media attachments.", len(newly_matched))
            for q in newly_matched[:20]:
                files = [a.filename for a in (q.question.media or [])]
                log.info("  [%s] %s", q.id, files)
            if len(newly_matched) > 20:
                log.info("  … and %d more.", len(newly_matched) - 20)
            return

        if not newly_matched:
            log.info("Nothing new to match.")
            return

        log.info("Writing %d matched questions to DB…", len(newly_matched))
        _upsert(newly_matched, conn)
        log.info("Re-exporting JSON files…")
        counts = stage6(
            conn, paths["output_dir"],
            members_config_path=paths["members_config"],
            session_overrides_path=paths["session_overrides_config"],
            state_path=paths["state_path"],
        )
        _log_counts(counts)
    finally:
        conn.close()
    log.info("enrich-media complete.")


def _run_upload_media(media_dir: str, dry_run: bool = False) -> None:
    """Upload matched media files to Cloudflare R2 and write URLs back to DB."""
    from utils.r2_upload import upload_media
    from utils.r2_usage import check_and_warn

    media_path = Path(media_dir)
    if not media_path.exists() or not media_path.is_dir():
        log.error("Media directory not found: %s", media_path)
        sys.exit(1)

    paths = _post_hoc_paths()
    db_path_obj = paths["db_path"]
    if not db_path_obj.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path_obj)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path_obj))
    try:
        log.info("Loading all questions from DB…")
        all_questions = _load_all(conn)
        pending = sum(
            1 for q in all_questions
            for att in (q.question.media or [])
            if att.filename and att.url is None
        )
        log.info("  Questions with unuploaded media: %d", pending)

        updated = upload_media(all_questions, media_path, dry_run=dry_run)

        if dry_run:
            return

        newly_with_url = [
            q for orig, q in zip(all_questions, updated)
            if any(
                (a.url is not None and oa.url is None)
                for a, oa in zip(q.question.media or [], orig.question.media or [])
            )
        ]

        if newly_with_url:
            log.info("Writing %d updated questions to DB…", len(newly_with_url))
            _upsert(newly_with_url, conn)
            log.info("Re-exporting JSON files…")
            counts = stage6(
                conn, paths["output_dir"],
                members_config_path=paths["members_config"],
                session_overrides_path=paths["session_overrides_config"],
                state_path=paths["state_path"],
            )
            _log_counts(counts)
        else:
            log.info("No new uploads — nothing to write.")

        # Always check R2 free-tier usage after an upload run
        log.info("Checking R2 free-tier usage…")
        r2_usage_path = paths["output_dir"] / "r2_usage.json"
        check_and_warn(output_path=r2_usage_path)

    finally:
        conn.close()
    log.info("upload-media complete.")


def _run_check_r2() -> None:
    """Check current R2 usage against free-tier limits and warn if close."""
    from utils.r2_usage import check_and_warn
    output_dir = V2_DIR / "visualizer" / "static" / "data"
    log.info("Checking R2 free-tier usage…")
    result = check_and_warn(output_path=output_dir / "r2_usage.json")
    if result.get("warnings"):
        sys.exit(1)   # non-zero exit so CI/scripts can detect the warning


def _run_cleanup_r2(dry_run: bool = False) -> None:
    """Delete R2 objects not referenced by any question in the DB."""
    import os
    try:
        import boto3
    except ImportError:
        log.error("boto3 required: pip install boto3")
        sys.exit(1)

    paths = _post_hoc_paths()
    db_path_obj = paths["db_path"]
    if not db_path_obj.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path_obj)
        sys.exit(1)

    # Collect every filename referenced in the DB (question + discussion media)
    conn = sqlite3.connect(str(db_path_obj))
    try:
        all_questions = _load_all(conn)
    finally:
        conn.close()

    referenced: set[str] = set()
    for q in all_questions:
        for att in q.question.media or []:
            if att.filename:
                referenced.add(att.filename)
        for d in q.discussion or []:
            for att in d.media or []:
                if att.filename:
                    referenced.add(att.filename)

    log.info("DB references %d unique media filename(s).", len(referenced))

    # List all objects in R2
    account_id        = os.environ.get("R2_ACCOUNT_ID", "")
    access_key_id     = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    bucket            = os.environ.get("R2_BUCKET", "")

    for var, name in [(account_id, "R2_ACCOUNT_ID"), (access_key_id, "R2_ACCESS_KEY_ID"),
                      (secret_access_key, "R2_SECRET_ACCESS_KEY"), (bucket, "R2_BUCKET")]:
        if not var:
            log.error("Missing env var: %s", name)
            sys.exit(1)

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )

    r2_keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            r2_keys.append(obj["Key"])

    log.info("R2 bucket contains %d object(s).", len(r2_keys))

    orphans = [k for k in r2_keys if k not in referenced]
    if not orphans:
        log.info("No orphaned objects found — R2 is clean.")
        return

    log.info("Found %d orphaned object(s) to delete:", len(orphans))
    for key in orphans:
        log.info("  %s%s", "[dry-run] " if dry_run else "", key)

    if dry_run:
        log.info("[dry-run] No deletions performed.")
        return

    # Delete in batches of 1000 (S3 delete_objects limit)
    deleted = 0
    for i in range(0, len(orphans), 1000):
        batch = [{"Key": k} for k in orphans[i:i + 1000]]
        resp = client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
        deleted += len(resp.get("Deleted", []))
        for err in resp.get("Errors", []):
            log.error("  Failed to delete %s: %s", err["Key"], err["Message"])

    log.info("Deleted %d/%d orphaned object(s) from R2.", deleted, len(orphans))

    # Refresh usage after cleanup
    from utils.r2_usage import check_and_warn
    r2_usage_path = paths["output_dir"] / "r2_usage.json"
    check_and_warn(output_path=r2_usage_path)


def _run_backfill_discussion(dry_run: bool = False) -> None:
    """Scan chat messages and add missing discussion entries to extracted questions."""
    import json as _json
    from utils.backfill_discussion import backfill

    config = load_config(_PIPELINE_DIR / "config")
    config = dict(config)
    config["chat_file"] = str(V2_DIR / config["chat_file"])
    aliases = load_aliases(_PIPELINE_DIR / "config")
    data_dir = V2_DIR / "data"
    extraction_dir = data_dir / "extraction_output"

    # Parse chat
    log.info("Parsing chat file…")
    chat_path = Path(config["chat_file"])
    lines = chat_path.read_text(encoding="utf-8").splitlines(keepends=True)
    messages = stage1(lines, config, aliases=aliases)
    log.info("  %s messages parsed.", f"{len(messages):,}")

    messages_by_date: dict[str, list[dict]] = defaultdict(list)
    for m in messages:
        messages_by_date[m["timestamp"][:10]].append(m)

    # Load extraction output files
    questions_by_date: dict[str, list[dict]] = {}
    for f in sorted(extraction_dir.iterdir()):
        if f.suffix != ".json":
            continue
        try:
            questions_by_date[f.stem] = _json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass

    log.info("Loaded extraction files for %d dates.", len(questions_by_date))
    log.info("Scanning for missing discussion entries…")

    results = backfill(questions_by_date, messages_by_date, dry_run=dry_run)

    if not results:
        log.info("No missing discussion entries found.")
        return

    total = sum(results.values())
    log.info("Found %d missing discussion entries across %d dates.", total, len(results))

    if dry_run:
        log.info("[dry-run] No files modified.")
        return

    # Write back to extraction_output files
    for date_str, entries in questions_by_date.items():
        if date_str not in results:
            continue
        out_path = extraction_dir / f"{date_str}.json"
        out_path.write_text(
            _json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("  [%s] Updated extraction file (+%d discussion entries)", date_str, results[date_str])

    # Re-run store + export to push changes to DB and JSON
    db_path = data_dir / "questions.db"
    state_path = data_dir / "pipeline_state.json"
    output_dir = V2_DIR / "visualizer" / "static" / "data"
    members_config = _PIPELINE_DIR / "config" / "members.json"
    session_overrides_config = _PIPELINE_DIR / "config" / "session_overrides.json"

    conn = sqlite3.connect(str(db_path))
    try:
        log.info("Re-structuring and storing updated questions…")
        for date_str in results:
            raw = questions_by_date[date_str]
            questions = stage3(raw, config)
            questions = stage4(questions, config)
            stage5(questions, conn, state_path=state_path)

        log.info("Re-exporting JSON…")
        counts = stage6(
            conn, output_dir,
            members_config_path=members_config,
            session_overrides_path=session_overrides_config,
            state_path=state_path,
        )
        _log_counts(counts)
    finally:
        conn.close()
    log.info("backfill-discussion complete.")


def _run_export_rejected() -> None:
    """Parse rejected-candidate .txt files and write combined JSON."""
    rejected_dir = V2_DIR / "data" / "rejected_candidates"
    output_path = V2_DIR / "visualizer" / "static" / "data" / "rejected_candidates.json"

    if not rejected_dir.exists():
        log.error("Rejected candidates directory not found: %s", rejected_dir)
        log.error("Run check-coverage first to generate rejected candidate files.")
        sys.exit(1)

    log.info("[export-rejected] Parsing .txt files from %s…", rejected_dir)
    count = _export_rejected(rejected_dir, output_path)
    log.info("[export-rejected] Wrote %d entries to %s", count, output_path)


def _run_check_coverage() -> None:
    """
    Cross-reference chat file, extraction_output/, and questions.db to find:
      - Dates in the chat with heuristic question candidates but no extraction file
      - Dates where the extracted count is suspiciously low vs heuristic candidates
      - Dates in extraction files but missing from the DB
    """
    import json as _json

    config = load_config(_PIPELINE_DIR / "config")
    config = dict(config)
    config["chat_file"] = str(V2_DIR / config["chat_file"])
    aliases = load_aliases(_PIPELINE_DIR / "config")

    data_dir = V2_DIR / "data"
    extraction_dir = data_dir / "extraction_output"
    db_path = data_dir / "questions.db"

    # Parse all messages
    log.info("Parsing chat file…")
    chat_path = Path(config["chat_file"])
    lines = chat_path.read_text(encoding="utf-8").splitlines(keepends=True)
    messages = stage1(lines, config, aliases=aliases)
    log.info("  %s messages parsed.", f"{len(messages):,}")

    # Group by date
    by_date: dict[str, list[dict]] = defaultdict(list)
    for m in messages:
        by_date[m["timestamp"][:10]].append(m)

    # Run heuristic prefilter on each date
    from stages.stage2_extract import prefilter
    heuristic: dict[str, int] = {}
    for date_str in sorted(by_date.keys()):
        candidates = prefilter(by_date[date_str], config)
        heuristic[date_str] = len(candidates)

    # Check extraction_output files
    extracted: dict[str, int] = {}
    if extraction_dir.exists():
        for f in sorted(extraction_dir.iterdir()):
            if f.suffix == ".json":
                date_str = f.stem
                try:
                    data = _json.loads(f.read_text(encoding="utf-8"))
                    extracted[date_str] = len(data)
                except Exception:
                    extracted[date_str] = -1  # corrupt file

    # Check DB
    db_counts: dict[str, int] = {}
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        for row in conn.execute("SELECT date, COUNT(*) FROM questions GROUP BY date"):
            db_counts[row[0]] = row[1]
        conn.close()

    # Write rejected candidates
    rejected_dir = data_dir / "rejected_candidates"
    _write_rejected_candidates(by_date, extraction_dir, rejected_dir, config)

    # Report
    all_dates = sorted(set(heuristic.keys()) | set(extracted.keys()) | set(db_counts.keys()))

    missing_extraction: list[str] = []
    low_extraction: list[tuple[str, int, int]] = []
    missing_db: list[tuple[str, int]] = []
    zero_but_candidates: list[tuple[str, int]] = []

    for d in all_dates:
        h = heuristic.get(d, 0)
        e = extracted.get(d)
        db = db_counts.get(d, 0)

        if h >= 3 and e is None:
            missing_extraction.append(d)
        elif e is not None and e == -1:
            missing_extraction.append(d)  # corrupt
        elif e is not None and e == 0 and h >= 5:
            zero_but_candidates.append((d, h))
        elif e is not None and e > 0 and h > 0:
            ratio = e / h
            if ratio < 0.08 and h >= 10:
                low_extraction.append((d, h, e))

        if e is not None and e > 0 and db == 0:
            missing_db.append((d, e))

    # Print results
    log.info("")
    log.info("═══ Coverage Report ═══")
    log.info("")
    log.info("  Total dates in chat: %d", len(heuristic))
    log.info("  Dates with extraction files: %d", len(extracted))
    log.info("  Dates with DB rows: %d", len(db_counts))
    log.info("  Total questions in DB: %d", sum(db_counts.values()))
    log.info("")

    if missing_extraction:
        log.warning("  MISSING EXTRACTION — dates with %s3 heuristic candidates but no extraction file:", "≥")
        for d in missing_extraction:
            log.warning("    %s  (%d heuristic candidates, %d messages)",
                        d, heuristic.get(d, 0), len(by_date.get(d, [])))
    else:
        log.info("  No missing extraction files.")

    if zero_but_candidates:
        log.warning("  ZERO EXTRACTED — extraction file exists but has 0 questions despite candidates:")
        for d, h in zero_but_candidates:
            log.warning("    %s  (%d heuristic candidates)", d, h)

    if low_extraction:
        log.warning("  LOW EXTRACTION — extracted count is suspiciously low vs heuristic candidates:")
        for d, h, e in low_extraction:
            log.warning("    %s  extracted=%d  heuristic=%d  (%.0f%%)", d, e, h, e / h * 100)

    if missing_db:
        log.warning("  MISSING FROM DB — extraction file exists but no DB rows:")
        for d, e in missing_db:
            log.warning("    %s  (%d in extraction file)", d, e)

    if not (missing_extraction or zero_but_candidates or low_extraction or missing_db):
        log.info("  Everything looks good!")

    # Summary table
    log.info("")
    log.info("  %-12s  %6s  %9s  %4s", "Date", "Hints", "Extracted", "DB")
    log.info("  %s", "-" * 40)
    for d in all_dates:
        h = heuristic.get(d, 0)
        e = extracted.get(d)
        db = db_counts.get(d, 0)
        e_str = str(e) if e is not None else "—"
        flag = ""
        if d in missing_extraction:
            flag = "  ← MISSING"
        elif (d, h) in [(x[0], x[1]) for x in zero_but_candidates]:
            flag = "  ← ZERO"
        elif any(x[0] == d for x in low_extraction):
            flag = "  ← LOW"
        elif (d, e or 0) in missing_db:
            flag = "  ← NO DB"
        if h > 0 or e is not None or db > 0:
            log.info("  %-12s  %6d  %9s  %4d%s", d, h, e_str, db, flag)


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

    p_media = sub.add_parser("enrich-media", help="Match media files from WhatsApp export directory to questions")
    p_media.add_argument("--media-dir", required=True, metavar="PATH", help="Directory containing exported WhatsApp media files (e.g. data/raw/)")
    p_media.add_argument("--dry-run", action="store_true", help="Show matches without writing anything")

    p_upload = sub.add_parser("upload-media", help="Upload matched media files to Cloudflare R2")
    p_upload.add_argument("--media-dir", required=True, metavar="PATH", help="Directory containing the local media files")
    p_upload.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")

    sub.add_parser("check-r2", help="Check R2 free-tier usage and warn if limits are close")

    p_cleanup = sub.add_parser("cleanup-r2", help="Delete R2 objects not referenced by any question in the DB")
    p_cleanup.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")

    p_reenrich = sub.add_parser("reenrich", help="Re-enrich questions with < 2 topics via LLM (Stage 4)")
    p_reenrich.add_argument("--dry-run", action="store_true", help="Show counts without writing anything")

    p_norm = sub.add_parser("normalize-tags", help="Strip format tags and rename near-duplicates in the DB")
    p_norm.add_argument("--dry-run", action="store_true", help="Show changes without writing anything")

    p_topics = sub.add_parser("assign-topics", help="Assign primary + secondary topics via rules (no LLM)")
    p_topics.add_argument("--dry-run", action="store_true", help="Show assignments without writing anything")

    sub.add_parser("export-rejected", help="Export rejected candidates from .txt files to JSON")
    p_backfill_disc = sub.add_parser("backfill-discussion", help="Add missing chat messages to extracted questions' discussion arrays")
    p_backfill_disc.add_argument("--dry-run", action="store_true", help="Show what would be added without modifying files")

    sub.add_parser("check-coverage", help="Check for missed dates or suspiciously low extraction counts")

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
        _run_enrich_media(args.media_dir, dry_run=args.dry_run)
    elif args.command == "upload-media":
        _run_upload_media(args.media_dir, dry_run=args.dry_run)
    elif args.command == "check-r2":
        _run_check_r2()
    elif args.command == "cleanup-r2":
        _run_cleanup_r2(args.dry_run)
    elif args.command == "reenrich":
        _run_reenrich(args.dry_run)
    elif args.command == "normalize-tags":
        _run_normalize_tags(args.dry_run)
    elif args.command == "assign-topics":
        _run_assign_topics(args.dry_run)
    elif args.command == "export-rejected":
        _run_export_rejected()
    elif args.command == "backfill-discussion":
        _run_backfill_discussion(args.dry_run)
    elif args.command == "check-coverage":
        _run_check_coverage()


if __name__ == "__main__":
    main()

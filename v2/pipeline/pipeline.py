"""
KVizzing v2 Pipeline CLI

Run from v2/pipeline/:

  python3 pipeline.py backfill          # process all dates not yet in the store
  python3 pipeline.py incremental       # process only dates after last_stored_date
  python3 pipeline.py export            # re-export JSON from questions.db (no LLM)
  python3 pipeline.py generate-images   # generate background images for new sessions
  python3 pipeline.py enrich-reactions --db PATH/TO/ChatStorage.sqlite
  python3 pipeline.py enrich-media     --media-dir PATH/TO/WhatsApp/Media
  python3 pipeline.py reenrich         [--dry-run] [--all]  # re-run LLM topic enrichment
  python3 pipeline.py normalize-tags   [--dry-run]  # strip format tags, fix near-duplicates in DB
  python3 pipeline.py assign-topics    [--dry-run]  # assign topics via rules (no LLM)
  python3 pipeline.py reimport [DATES...]  # re-import extraction_output into DB (no LLM)
  python3 pipeline.py export-rejected                # export rejected candidates to JSON

All file paths in pipeline_config.json are resolved relative to v2/ (the parent
of this script's directory). Logs are written to pipeline/logs/YYYY-MM-DD.log.
"""

from __future__ import annotations

import argparse
import os
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

from utils.log_setup import setup as _setup_logging

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
from utils.reclassify_elaboration import run_on_file as _reclassify_elaboration
from utils.detect_sessions import detect_sessions as _detect_sessions, apply_sessions as _apply_sessions
from utils.detect_connect_quizzes import main as _detect_connect_main


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
    Write rejected-candidate JSON files for dates that have extraction files.
    Compares heuristic prefilter candidates against extracted questions to find
    candidates the LLM chose not to extract.
    """
    import json as _json
    from datetime import datetime as _dt
    from stages.stage2_extract import prefilter

    rejected_dir.mkdir(parents=True, exist_ok=True)

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

        # Bundle into threads
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

        total_rejected += sum(len(t) for t in threads)
        total_threads += len(threads)

        # Build JSON output
        date_threads = []
        for ti, thread in enumerate(threads, 1):
            first_idx = thread[0][0]
            last_idx = thread[-1][0]
            ctx_start = max(0, first_idx - 8)
            ctx_end = min(len(day_messages), last_idx + 13)
            candidate_idxs = {idx for idx, _ in thread}

            candidates_json = []
            for idx, msg in thread:
                reason = (
                    "question_mark" if msg["text"].strip().endswith("?") else
                    "question_prefix" if any(msg["text"].strip().upper().startswith(p) for p in ["Q.", "Q:", "Q ", "FLASH Q", "QUESTION"]) else
                    "media_short_text" if msg.get("has_media") else
                    "session_marker"
                )
                candidates_json.append({
                    "timestamp": msg["timestamp"],
                    "username": msg["username"],
                    "text": msg["text"][:300],
                    "reason_flagged": reason,
                })

            context_json = []
            for ci in range(ctx_start, ctx_end):
                m = day_messages[ci]
                context_json.append({
                    "timestamp": m["timestamp"],
                    "username": m["username"],
                    "text": m["text"][:200],
                    "is_candidate": ci in candidate_idxs,
                })

            date_threads.append({
                "id": f"{date_str}-t{ti}",
                "date": date_str,
                "thread_number": ti,
                "candidates": candidates_json,
                "context": context_json,
            })

        (rejected_dir / f"{date_str}.json").write_text(
            _json.dumps(date_threads, indent=2, ensure_ascii=False), encoding="utf-8"
        )

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
        log.error("No LLM client available. Set GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY, or USE_OLLAMA=1.")
        sys.exit(1)

    log.info("=" * 60)
    log.info("Pipeline run  mode=%s", mode)
    log.info("=" * 60)

    db = sqlite3.connect(str(db_path))
    try:
        # Stage 0 — Filter
        log.info("[Stage 0] Filtering lines (%s)…", mode)
        lines = stage0(config, db, mode=mode, extraction_output_dir=extraction_output_dir)
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
                except Exception as e:
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

                # Save LLM-rejected candidates to attribution_gaps/rejected_candidates/
                from stages.stage2_extract import get_rejected
                rejected = get_rejected(date_str)
                if rejected:
                    gaps_dir = data_dir / "attribution_gaps" / "rejected_candidates"
                    gaps_dir.mkdir(parents=True, exist_ok=True)
                    rejected_file = gaps_dir / f"{date_str}.json"
                    rejected_file.write_text(
                        _json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    log.debug("  [%s] Saved %d rejected candidates to attribution_gaps/", date_str, len(rejected))

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

            # Per-date media matching
            media_dir = V2_DIR / "data" / "raw"
            if media_dir.is_dir():
                try:
                    from utils.media_match import match_media
                    date_qs_with_media = [q for q in questions if q.question.has_media and q.question.media is None]
                    if date_qs_with_media:
                        enriched = match_media(date_qs_with_media, media_dir, config)
                        matched = [q for q in enriched if q.question.media is not None]
                        if matched:
                            _upsert(matched, db)
                            log.debug("  [%s] Matched %d media files.", date_str, len(matched))
                except Exception as e:
                    log.debug("  [%s] Media match skipped: %s", date_str, e)

            # Per-date export
            try:
                counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
            except Exception as e:
                log.warning("  [%s] Export failed: %s", date_str, e)

            # Per-date rejected candidates + export
            try:
                rejected_dir = data_dir / "attribution_gaps" / "rejected_candidates"
                _write_rejected_candidates({date_str: by_date.get(date_str, [])}, extraction_output_dir, rejected_dir, config)
                rejected_json = output_dir / "rejected_candidates.json"
                if rejected_dir.exists():
                    _export_rejected(rejected_dir, rejected_json)
            except Exception as e:
                log.debug("  [%s] Rejected candidates skipped: %s", date_str, e)

            # Per-date session image generation
            try:
                _generate_images_main()
            except Exception as e:
                log.debug("  [%s] Image generation skipped: %s", date_str, e)

        log.info("")
        log.info("[Stage 5] Done — %s questions stored.", f"{total_stored:,}")

        if skipped_dates:
            log.warning(
                "%d date(s) skipped due to unresolvable extraction errors: %s",
                len(skipped_dates), ", ".join(skipped_dates),
            )
            log.warning("Re-run with a different LLM or manually fix extraction_output files for these dates.")

        # Final export (captures any remaining changes)
        log.info("[Stage 6] Final export…")
        counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
        _log_counts(counts)

        # Rejected candidates
        log.info("[Rejected] Writing rejected candidate files…")
        rejected_dir = data_dir / "attribution_gaps" / "rejected_candidates"
        _write_rejected_candidates(by_date, extraction_output_dir, rejected_dir, config)
        rejected_json = output_dir / "rejected_candidates.json"
        if rejected_dir.exists():
            count = _export_rejected(rejected_dir, rejected_json)
            log.info("  Exported %d rejected entries to %s", count, rejected_json.name)

        # Log unmatched media — questions with has_media=true but no matched files
        try:
            import json as _json_um
            all_qs = _load_all(db)
            unmatched_media = []
            for q in all_qs:
                if q.question.has_media and q.question.media is None:
                    unmatched_media.append({
                        "id": q.id,
                        "date": str(q.date),
                        "timestamp": str(q.question.timestamp),
                        "asker": q.question.asker,
                        "text": q.question.text[:200],
                    })
            gaps_dir = data_dir / "attribution_gaps"
            gaps_dir.mkdir(parents=True, exist_ok=True)
            unmatched_path = gaps_dir / "unmatched_media.json"
            unmatched_path.write_text(_json_um.dumps(unmatched_media, indent=2, ensure_ascii=False))
            if unmatched_media:
                log.info("[Media] %d questions with has_media=true but no matched file → %s",
                         len(unmatched_media), unmatched_path.name)
        except Exception as e:
            log.warning("Unmatched media log failed (non-fatal): %s", e)

        # Upload media to R2 (if R2 env vars are configured)
        if media_dir.is_dir() and os.environ.get("R2_BUCKET"):
            try:
                from utils.r2_upload import upload_media
                log.info("[R2] Uploading new media to Cloudflare R2…")
                all_questions = _load_all(db)
                needs_upload = any(
                    att.filename and att.url is None
                    for q in all_questions
                    for att in (q.question.media or [])
                )
                if needs_upload:
                    updated = upload_media(all_questions, media_dir)
                    uploaded_qs = [q for q in updated if any(
                        att.url for att in (q.question.media or [])
                    )]
                    if uploaded_qs:
                        _upsert(uploaded_qs, db)
                        counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
                        log.info("  R2 upload complete, re-exported.")
                else:
                    log.info("  No pending media uploads.")
            except Exception as e:
                log.warning("R2 upload failed (non-fatal): %s", e)

        # Generate session images for new sessions
        try:
            log.info("[Images] Generating session images…")
            _generate_images_main()
        except Exception as e:
            log.warning("Session image generation failed (non-fatal): %s", e)

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


def _run_reenrich(dry_run: bool, all_questions_flag: bool = False) -> None:
    """Re-enrich questions via LLM (Stage 4). Use --all to recategorize everything."""
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
        if all_questions_flag:
            needs = all_questions
            log.info("  Re-enriching ALL %d questions (--all flag).", len(needs))
        else:
            needs = [q for q in all_questions if len(q.question.topics) < 2]
            log.info("  Need (re-)enrichment (< 2 topics): %d", len(needs))

        if dry_run:
            log.info("Dry run — exiting without changes.")
            return

        client = get_client()
        if client is None:
            log.error("No LLM client available. Set USE_OLLAMA=1, GROQ_API_KEY, or ANTHROPIC_API_KEY.")
            sys.exit(1)

        log.info("Running Stage 4 enrichment%s…", " (fresh recategorization)" if all_questions_flag else "")
        enriched = _stage4_enrich(needs, config, client, fresh=all_questions_flag)
        gained = sum(1 for q in enriched if len(q.question.topics) >= 2)
        log.info("  %d questions now have 2+ topics", gained)
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
        two_topics = sum(1 for q in enriched if len(q.question.topics) == 2)
        three_topics = sum(1 for q in enriched if len(q.question.topics) >= 3)
        log.info("  No topic:    %d", no_topic)
        log.info("  1 topic:     %d", one_topic)
        log.info("  2 topics:    %d", two_topics)
        log.info("  3 topics:    %d", three_topics)

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

    total_backfilled = sum(results.values()) if results else 0
    if total_backfilled:
        log.info("Found %d missing discussion entries across %d dates.", total_backfilled, len(results))
    else:
        log.info("No missing discussion entries found.")

    # Reclassify existing discussion roles with improved heuristics
    from utils.backfill_discussion import reclassify
    log.info("Reclassifying discussion roles…")
    reclass_results = reclassify(questions_by_date, dry_run=dry_run)
    total_reclassified = sum(reclass_results.values()) if reclass_results else 0
    if total_reclassified:
        log.info("Reclassified %d discussion entries across %d dates.", total_reclassified, len(reclass_results))
    else:
        log.info("No discussion entries needed reclassification.")

    # Merge affected dates
    affected_dates = set(results.keys()) | set(reclass_results.keys())
    if not affected_dates:
        return

    if dry_run:
        log.info("[dry-run] No files modified.")
        return

    # Write back to extraction_output files
    for date_str in affected_dates:
        entries = questions_by_date.get(date_str)
        if not entries:
            continue
        out_path = extraction_dir / f"{date_str}.json"
        out_path.write_text(
            _json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        parts = []
        if date_str in results:
            parts.append(f"+{results[date_str]} new")
        if date_str in reclass_results:
            parts.append(f"{reclass_results[date_str]} reclassified")
        log.info("  [%s] Updated extraction file (%s)", date_str, ", ".join(parts))

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


def _run_classify_discussion(dry_run: bool = False, date_filter: str | None = None, skip: int = 0) -> None:
    """Use LLM to classify discussion entry roles."""
    import json as _json
    from utils.classify_discussion import classify_discussion

    data_dir = V2_DIR / "data"
    extraction_dir = data_dir / "extraction_output"

    client = get_client()
    if not client:
        log.error("No LLM client available. Set GEMINI_API_KEY, GROQ_API_KEY, or USE_OLLAMA=1.")
        sys.exit(1)

    # Load extraction output files
    questions_by_date: dict[str, list[dict]] = {}
    for f in sorted(extraction_dir.iterdir()):
        if f.suffix != ".json":
            continue
        if date_filter and f.stem != date_filter:
            continue
        try:
            questions_by_date[f.stem] = _json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass

    if skip > 0:
        all_dates = sorted(questions_by_date.keys())
        skipped = all_dates[:skip]
        for d in skipped:
            del questions_by_date[d]
        log.info("Skipped first %d dates (up to %s).", len(skipped), skipped[-1] if skipped else "—")

    log.info("Loaded extraction files for %d dates.", len(questions_by_date))
    log.info("Classifying discussion roles with LLM…")

    results = classify_discussion(questions_by_date, client, dry_run=dry_run)

    total = sum(results.values()) if results else 0
    if total:
        log.info("Reclassified %d discussion entries across %d dates.", total, len(results))
    else:
        log.info("No discussion entries needed reclassification.")
        return

    if dry_run:
        log.info("[dry-run] No files modified.")
        return

    # Write back to extraction_output files
    for date_str in results:
        entries = questions_by_date.get(date_str)
        if not entries:
            continue
        out_path = extraction_dir / f"{date_str}.json"
        out_path.write_text(
            _json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Re-import affected dates to DB + re-export
    config = load_config(_PIPELINE_DIR / "config")
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
    log.info("classify-discussion complete.")


def _run_reimport(dates: list[str]) -> None:
    """Re-import extraction_output files into the DB (audit + auto-fix + stages 3-6, no LLM)."""
    import json as _json
    from utils.audit_extraction import audit_data, _is_explicit_confirm

    config = load_config(_PIPELINE_DIR / "config")
    config = dict(config)
    config["chat_file"] = str(V2_DIR / config["chat_file"])

    data_dir = V2_DIR / "data"
    output_dir = V2_DIR / "visualizer" / "static" / "data"
    db_path = data_dir / "questions.db"
    errors_dir = data_dir / "errors"
    state_path = data_dir / "pipeline_state.json"
    members_config = _PIPELINE_DIR / "config" / "members.json"
    session_overrides_config = _PIPELINE_DIR / "config" / "session_overrides.json"
    extraction_output_dir = data_dir / "extraction_output"

    FORMAT_TAGS = {
        "identify", "anagram", "wordplay", "connect", "clickbait",
        "real life", "naming", "weird", "pun", "battle",
        "fill in the blank", "multi-part", "factual",
    }
    MEDIA_MARKERS = {"image omitted", "gif omitted", "video omitted",
                     "audio omitted", "document omitted"}

    if not db_path.exists():
        log.error("questions.db not found at %s — run backfill first.", db_path)
        sys.exit(1)

    # If no dates specified, reimport all extraction files
    if not dates:
        dates = sorted(f.stem for f in extraction_output_dir.glob("????-??-??.json"))

    log.info("=" * 60)
    log.info("Reimport  %d date(s)", len(dates))
    log.info("=" * 60)

    # ── Auto-fix pass on all files before importing ──
    total_fixes = 0
    for date_str in dates:
        extraction_file = extraction_output_dir / f"{date_str}.json"
        if not extraction_file.exists():
            continue
        try:
            data = _json.loads(extraction_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not data:
            continue

        from utils.config import load_topics as _load_topics, load_topic_aliases as _load_aliases
        _VALID_TOPIC_IDS, _ = _load_topics(_PIPELINE_DIR / "config")
        _TOPIC_ALIASES = _load_aliases(_PIPELINE_DIR / "config")

        fixes = 0
        for q in data:
            disc = q.get("discussion", [])

            # Fix INVALID_TOPIC
            if "topics" in q and isinstance(q["topics"], list):
                new_topics = [_TOPIC_ALIASES.get(t.lower(), t) for t in q["topics"]]
                if new_topics != q["topics"]:
                    q["topics"] = new_topics
                    fixes += 1

            # Fix FORMAT_TAG
            tags = q.get("tags") or []
            clean_tags = [t for t in tags if t.lower() not in FORMAT_TAGS]
            if len(clean_tags) != len(tags):
                q["tags"] = clean_tags
                fixes += 1

            # Fix TAG_VARIANT
            if q.get("tags"):
                new_tags = ["badly explained" if t.lower() == "badly explained plots" else t for t in q["tags"]]
                if new_tags != q["tags"]:
                    q["tags"] = new_tags
                    fixes += 1

            # Fix ARTIFACT — strip ↵ and edit markers
            for field in ("question_text", "answer_text", "confirmation_text"):
                val = q.get(field) or ""
                if val:
                    cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                    if cleaned != val:
                        q[field] = cleaned if cleaned else None
                        fixes += 1
            for e in disc:
                val = e.get("text") or ""
                if val:
                    cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                    if cleaned != val:
                        e["text"] = cleaned
                        fixes += 1

            # Fix ORPHAN_SESSION_VAR
            if not q.get("is_session_question"):
                for sf in ("session_quizmaster", "session_theme", "session_quiz_type", "session_connect_answer", "session_question_number", "session_announcement"):
                    if q.get(sf):
                        q[sf] = None
                        fixes += 1

            # Fix COLLAB_MISMATCH
            parts = q.get("answer_parts") or []
            if parts and not q.get("answer_is_collaborative"):
                solvers = {p["solver"] for p in parts if p.get("solver")}
                if len(solvers) > 1:
                    q["answer_is_collaborative"] = True
                    fixes += 1

            # Fix confidence/confirmed consistency
            if q.get("answer_confirmed"):
                if q.get("extraction_confidence") != "high":
                    q["extraction_confidence"] = "high"
                    fixes += 1
            else:
                if q.get("extraction_confidence") == "high":
                    q["extraction_confidence"] = "medium"
                    fixes += 1

            # Fix SOLVER_MISMATCH / TIMESTAMP_MISMATCH
            solver = q.get("answer_solver")
            if solver and not q.get("answer_is_collaborative") and disc:
                first_correct = next((e for e in disc if e.get("is_correct") is True), None)
                if first_correct:
                    if first_correct["username"] != solver:
                        q["answer_solver"] = first_correct["username"]
                        fixes += 1
                    if first_correct.get("timestamp") != q.get("answer_timestamp"):
                        q["answer_timestamp"] = first_correct["timestamp"]
                        fixes += 1

            # Fix WRONG_CONFIRMER — non-asker confirmation
            asker = q.get("question_asker")
            if asker:
                for e in disc:
                    if e.get("role") == "confirmation" and e.get("username") != asker:
                        e["role"] = "chat"
                        e["is_correct"] = None
                        fixes += 1

            # Fix MEDIA_MARKER in confirmation_text
            ct = q.get("confirmation_text") or ""
            if ct:
                ct_clean = ct
                for marker in MEDIA_MARKERS:
                    ct_clean = ct_clean.replace(marker, "").replace(marker.title(), "")
                ct_clean = ct_clean.strip()
                if ct_clean != ct:
                    q["confirmation_text"] = ct_clean if ct_clean else None
                    fixes += 1

            # Fix has_media on wrong discussion roles
            for e in disc:
                if e.get("has_media") and e.get("role") not in ("hint", "answer_reveal", "elaboration"):
                    e["has_media"] = False
                    fixes += 1

            # Fix CONFIRM_NO_ROLE
            if q.get("answer_confirmed") and not any(e.get("role") == "confirmation" for e in disc):
                conf_text = (q.get("confirmation_text") or "").strip()
                asker = q.get("question_asker")
                matched = False
                for e in disc:
                    if (e.get("role") == "chat" and e.get("username") == asker
                            and (not conf_text or e.get("text", "").strip() == conf_text)):
                        e["role"] = "confirmation"
                        e["is_correct"] = None
                        matched = True
                        fixes += 1
                        break
                if not matched:
                    q["answer_confirmed"] = False
                    q["confirmation_text"] = None
                    q["extraction_confidence"] = "medium"
                    fixes += 1

            # Fix CONFIRM_IMPLICIT — reject false confirmations
            if q.get("answer_confirmed") and q.get("confirmation_text"):
                if not _is_explicit_confirm(q["confirmation_text"]):
                    q["answer_confirmed"] = False
                    q["confirmation_text"] = None
                    q["extraction_confidence"] = "medium"
                    for e in disc:
                        if e.get("role") == "confirmation":
                            e["role"] = "chat"
                            e["is_correct"] = None
                    fixes += 1

        if fixes:
            extraction_file.write_text(_json.dumps(data, indent=2, ensure_ascii=False))
            log.info("  [%s] Auto-fixed %d issue(s) in extraction file.", date_str, fixes)
            total_fixes += fixes

    if total_fixes:
        log.info("Auto-fix pass: %d total fixes across all files.", total_fixes)

    # ── Reclassify elaboration entries ──
    reclass_total = 0
    for date_str in dates:
        ext_file = extraction_output_dir / f"{date_str}.json"
        if ext_file.exists():
            count = _reclassify_elaboration(ext_file)
            if count:
                reclass_total += count
    if reclass_total:
        log.info("Reclassified %d chat→elaboration entries.", reclass_total)

    # ── Import into DB ──
    db = sqlite3.connect(str(db_path))
    total_stored = 0
    try:
        for date_str in dates:
            extraction_file = extraction_output_dir / f"{date_str}.json"
            if not extraction_file.exists():
                log.warning("  [%s] No extraction_output file — skipping.", date_str)
                continue
            try:
                candidates = _json.loads(extraction_file.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("  [%s] Failed to read file: %s — skipping.", date_str, e)
                continue
            if not candidates:
                log.debug("  [%s] Empty file — skipping.", date_str)
                continue

            # Verify clean after auto-fix
            remaining = audit_data(candidates)
            if remaining:
                log.warning("  [%s] %d audit issue(s) remain after auto-fix:", date_str, len(remaining))
                for issue in remaining:
                    log.warning("    %s", issue)

            # Stage 3 — Structure
            questions = stage3(candidates, config, errors_dir=errors_dir)
            questions = [q for q in questions if str(q.date) == date_str]
            if not questions:
                log.debug("  [%s] 0 valid questions after structuring.", date_str)
                continue

            # Stage 4 — Enrich (uses topic/tag rules, no LLM needed)
            questions = stage4(questions, config)

            # Stage 5 — Store (upsert — updates existing, inserts new)
            count = stage5(questions, db, state_path=state_path)
            total_stored += count
            log.info("  [%s] %d questions upserted.", date_str, count)

        log.info("Reimport done — %d questions upserted across %d date(s).", total_stored, len(dates))

        # Clean stale FTS entries
        stale = db.execute(
            "SELECT COUNT(*) FROM questions_fts WHERE rowid NOT IN (SELECT rowid FROM questions)"
        ).fetchone()[0]
        if stale:
            db.execute("DELETE FROM questions_fts WHERE rowid NOT IN (SELECT rowid FROM questions)")
            db.commit()
            log.info("  Cleaned %d stale FTS entries.", stale)

        # Stage 6 — Export
        log.info("[Stage 6] Exporting JSON files…")
        output_dir.mkdir(parents=True, exist_ok=True)
        counts = stage6(db, output_dir, members_config_path=members_config, session_overrides_path=session_overrides_config, state_path=state_path)
        _log_counts(counts)
    finally:
        db.close()


def _run_export_rejected() -> None:
    """Parse rejected-candidate .txt files and write combined JSON."""
    rejected_dir = V2_DIR / "data" / "attribution_gaps" / "rejected_candidates"
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
    rejected_dir = data_dir / "attribution_gaps" / "rejected_candidates"
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

    p_reenrich = sub.add_parser("reenrich", help="Re-enrich questions via LLM (Stage 4)")
    p_reenrich.add_argument("--dry-run", action="store_true", help="Show counts without writing anything")
    p_reenrich.add_argument("--all", action="store_true", help="Recategorize ALL questions (not just those with < 2 topics)")

    p_norm = sub.add_parser("normalize-tags", help="Strip format tags and rename near-duplicates in the DB")
    p_norm.add_argument("--dry-run", action="store_true", help="Show changes without writing anything")

    p_topics = sub.add_parser("assign-topics", help="Assign primary + secondary topics via rules (no LLM)")
    p_topics.add_argument("--dry-run", action="store_true", help="Show assignments without writing anything")

    sub.add_parser("export-rejected", help="Export rejected candidates from .txt files to JSON")
    p_backfill_disc = sub.add_parser("backfill-discussion", help="Add missing chat messages to extracted questions' discussion arrays")
    p_backfill_disc.add_argument("--dry-run", action="store_true", help="Show what would be added without modifying files")

    p_detect = sub.add_parser("detect-sessions", help="Detect informal quiz sessions in extraction files")
    p_detect.add_argument("--dry-run", action="store_true", help="Show detections without modifying files")
    p_detect.add_argument("--min-questions", type=int, default=4, help="Minimum questions for a session (default: 4)")
    p_detect.add_argument("--max-gap", type=float, default=30.0, help="Max minutes between consecutive Qs (default: 30)")

    p_detect_connect = sub.add_parser("detect-connect", help="Detect connect quizzes among sessions using LLM")
    p_detect_connect.add_argument("--apply", action="store_true", help="Write to session_overrides.json")

    p_reimport = sub.add_parser("reimport", help="Re-import extraction_output files into DB (stages 3-6, no LLM)")
    p_reimport.add_argument("dates", nargs="*", metavar="YYYY-MM-DD", help="Dates to reimport (default: all)")

    p_classify_disc = sub.add_parser("classify-discussion", help="Use LLM to classify discussion entry roles (attempt/hint/chat/elaboration/etc)")
    p_classify_disc.add_argument("--dry-run", action="store_true", help="Show changes without writing anything")
    p_classify_disc.add_argument("--date", type=str, metavar="YYYY-MM-DD", help="Only classify a specific date")
    p_classify_disc.add_argument("--skip", type=int, default=0, metavar="N", help="Skip the first N dates (already processed)")

    sub.add_parser("check-coverage", help="Check for missed dates or suspiciously low extraction counts")
    sub.add_parser("audit-quality", help="Find potentially non-question extractions and low-quality entries")

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
        _run_reenrich(args.dry_run, all_questions_flag=getattr(args, 'all', False))
    elif args.command == "normalize-tags":
        _run_normalize_tags(args.dry_run)
    elif args.command == "assign-topics":
        _run_assign_topics(args.dry_run)
    elif args.command == "export-rejected":
        _run_export_rejected()
    elif args.command == "backfill-discussion":
        _run_backfill_discussion(args.dry_run)
    elif args.command == "detect-sessions":
        from utils.detect_sessions import main as _detect_sessions_main
        sys.argv = [sys.argv[0]] + (['--dry-run'] if args.dry_run else []) + \
                   ['--min-questions', str(args.min_questions), '--max-gap', str(args.max_gap)]
        _detect_sessions_main()
    elif args.command == "reimport":
        _run_reimport(args.dates)
    elif args.command == "check-coverage":
        _run_check_coverage()
    elif args.command == "detect-connect":
        sys.argv = [sys.argv[0]] + (['--apply'] if args.apply else [])
        _detect_connect_main()
        if args.apply:
            log.info("Re-exporting after connect quiz detection…")
            _run_export()
    elif args.command == "classify-discussion":
        _run_classify_discussion(dry_run=args.dry_run, date_filter=args.date, skip=args.skip)
    elif args.command == "audit-quality":
        from utils.audit_quality import main as _audit_quality_main
        _audit_quality_main()


if __name__ == "__main__":
    main()

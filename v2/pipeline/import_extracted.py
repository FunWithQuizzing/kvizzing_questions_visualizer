"""
Import manually-extracted Q&A pairs into questions.db.

Run from v2/pipeline/:

  python3 import_extracted.py

Reads all YYYY-MM-DD.json files from v2/data/extraction_output/,
runs each through stages 3-5 (structure → store), then runs stage 6 (export).

Each output file should contain a JSON array of raw Q&A pair dicts in the
same format as the stage 2 LLM output schema.

Already-imported dates are skipped (questions.db id is stable, so re-importing
is safe but wasteful — use --force to override).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).parent
V2_DIR = _PIPELINE_DIR.parent

sys.path.insert(0, str(_PIPELINE_DIR))
sys.path.insert(0, str(V2_DIR / "schema"))

from utils.logging import setup as _setup_logging

log = _setup_logging(_PIPELINE_DIR / "logs")

from utils.config import load_config
from stages.stage3_structure import run as stage3
from stages.stage4_enrich import run as stage4
from stages.stage5_store import run as stage5
from stages.stage6_export import run as stage6
from clients.llm import get_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Import extracted Q&A pairs into questions.db")
    parser.add_argument("--force", action="store_true", help="Re-import all dates, even if already stored")
    parser.add_argument("--no-enrich", action="store_true", help="Skip LLM topic enrichment (stage 4)")
    args = parser.parse_args()

    config = load_config(_PIPELINE_DIR / "config")

    input_dir = V2_DIR / "data" / "extraction_output"
    data_dir = V2_DIR / "data"
    db_path = data_dir / "questions.db"
    errors_dir = data_dir / "errors"
    state_path = data_dir / "pipeline_state.json"
    members_config = _PIPELINE_DIR / "config" / "members.json"

    if not input_dir.exists():
        log.error("extraction_output/ not found at %s", input_dir)
        sys.exit(1)

    input_files = sorted(input_dir.glob("????-??-??.json"))
    if not input_files:
        log.error("No YYYY-MM-DD.json files found in %s", input_dir)
        sys.exit(1)

    log.info("=" * 60)
    log.info("Import run — %d files found", len(input_files))
    log.info("=" * 60)

    llm_client = None if args.no_enrich else get_client()
    if llm_client is None and not args.no_enrich:
        log.warning("No LLM client — skipping topic enrichment (stage 4).")

    db = sqlite3.connect(str(db_path))
    total_stored = 0

    try:
        for path in input_files:
            date_str = path.stem  # YYYY-MM-DD

            try:
                raw_pairs = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.error("  [%s] Failed to read %s: %s", date_str, path.name, e)
                continue

            if not isinstance(raw_pairs, list) or not raw_pairs:
                log.info("  [%s] Empty — skipping.", date_str)
                continue

            # Stage 3 — Structure
            questions = stage3(raw_pairs, config, errors_dir=errors_dir)
            questions = [q for q in questions if str(q.date) == date_str]
            if not questions:
                log.info("  [%s] 0 valid questions after structuring.", date_str)
                continue

            # Stage 4 — Enrich (topic + tags)
            questions = stage4(questions, config, llm_client=llm_client)

            # Stage 5 — Store
            count = stage5(questions, db, state_path=state_path)
            total_stored += count
            log.info("  [%s] %d questions stored (running total: %d)", date_str, count, total_stored)

        log.info("")
        log.info("Import done — %d questions stored total.", total_stored)

        # Stage 6 — Export JSON files
        log.info("[Stage 6] Exporting JSON files…")
        counts = stage6(db, data_dir, members_config_path=members_config, state_path=state_path)
        for key, val in counts.items():
            log.info("  %s: %s", key, f"{val:,}")

    except Exception:
        log.exception("Import crashed.")
        raise
    finally:
        db.close()
        log.info("Done.")


if __name__ == "__main__":
    main()

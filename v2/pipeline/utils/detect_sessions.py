"""
Post-hoc session detector.

Scans extraction_output files for informal sessions that the LLM missed:
groups of 4+ questions by the same asker within a time window.

Usage:
    python3 utils/detect_sessions.py [--dry-run] [--min-questions N] [--window-hours H]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


def detect_sessions(
    data: list[dict],
    min_questions: int = 4,
    max_gap_minutes: float = 30.0,
) -> list[dict]:
    """
    Detect informal sessions in extraction data.

    A session is a cluster of questions by the same asker where each consecutive
    pair is at most max_gap_minutes apart. Requires min_questions in the cluster.

    Returns list of detected sessions:
      [{ "quizmaster": str, "indices": [int], "theme": str|None }]
    """
    if not data:
        return []

    # Only consider questions NOT already tagged as session
    candidates: list[tuple[int, dict]] = []
    for i, q in enumerate(data):
        if not q.get("is_session_question"):
            candidates.append((i, q))

    if not candidates:
        return []

    # Group by asker
    by_asker: dict[str, list[tuple[int, dict]]] = {}
    for i, q in candidates:
        asker = q.get("question_asker", "")
        if asker:
            by_asker.setdefault(asker, []).append((i, q))

    detected = []
    gap_limit = timedelta(minutes=max_gap_minutes)

    for asker, entries in by_asker.items():
        if len(entries) < min_questions:
            continue

        # Sort by timestamp
        entries.sort(key=lambda x: x[1].get("question_timestamp", ""))

        # Cluster by consecutive gap: break when gap > max_gap_minutes
        cluster: list[tuple[int, dict]] = [entries[0]]
        for j in range(1, len(entries)):
            try:
                prev_ts = datetime.fromisoformat(
                    cluster[-1][1]["question_timestamp"].rstrip("Z")
                )
                curr_ts = datetime.fromisoformat(
                    entries[j][1]["question_timestamp"].rstrip("Z")
                )
                if curr_ts - prev_ts <= gap_limit:
                    cluster.append(entries[j])
                else:
                    if len(cluster) >= min_questions:
                        detected.append({
                            "quizmaster": asker,
                            "indices": [idx for idx, _ in cluster],
                            "theme": _infer_theme(cluster),
                        })
                    cluster = [entries[j]]
            except (ValueError, KeyError):
                cluster = [entries[j]]

        if len(cluster) >= min_questions:
            detected.append({
                "quizmaster": asker,
                "indices": [idx for idx, _ in cluster],
                "theme": _infer_theme(cluster),
            })

    return detected


def _infer_theme(cluster: list[tuple[int, dict]]) -> str | None:
    """Try to infer a session theme from question patterns."""
    texts = [q.get("question_text", "").lower() for _, q in cluster]
    tags = []
    for _, q in cluster:
        tags.extend(q.get("tags") or [])

    # Check for common tag patterns
    from collections import Counter
    tag_counts = Counter(t.lower() for t in tags)
    if tag_counts:
        top_tag, top_count = tag_counts.most_common(1)[0]
        if top_count >= len(cluster) * 0.5:  # majority share a tag
            return top_tag.replace("_", " ").title()

    # Check if most questions have media (image quiz)
    media_count = sum(1 for _, q in cluster if q.get("has_media"))
    if media_count >= len(cluster) * 0.7:
        return None  # media-heavy but can't determine theme from text

    return None


def _make_qm_slug(quizmaster: str) -> str:
    """Generate a quizmaster slug consistent with stage3_structure.py."""
    import re
    return re.split(r"[\s.]", quizmaster.lower())[0] if quizmaster else "unknown"


def apply_sessions(data: list[dict], sessions: list[dict], date_str: str) -> int:
    """Apply detected sessions to extraction data. Returns number of questions updated."""
    # Collect existing session IDs from LLM-tagged questions to avoid collisions
    existing_ids: set[str] = set()
    for q in data:
        if q.get("is_session_question") and q.get("session_quizmaster"):
            slug = _make_qm_slug(q["session_quizmaster"])
            existing_ids.add(f"{date_str}-{slug}")

    updated = 0
    used_ids: dict[str, int] = {}  # track how many times each base ID is used

    for session in sessions:
        qm = session["quizmaster"]
        theme = session["theme"]
        qm_slug = _make_qm_slug(qm)
        base_id = f"{date_str}-{qm_slug}"

        # Disambiguate: if base_id already exists (from LLM or earlier detection), add suffix
        if base_id in existing_ids or base_id in used_ids:
            count = used_ids.get(base_id, 1) + 1
            used_ids[base_id] = count
            session_id = f"{base_id}-{count}"
        else:
            session_id = base_id
            used_ids[base_id] = 1

        existing_ids.add(session_id)

        for qi, idx in enumerate(session["indices"]):
            q = data[idx]
            q["is_session_question"] = True
            q["session_quizmaster"] = qm
            q["session_theme"] = theme
            q["session_question_number"] = qi + 1
            # Don't overwrite session_quiz_type if already set
            if not q.get("session_quiz_type"):
                q["session_quiz_type"] = None
            updated += 1

    return updated


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Detect informal quiz sessions")
    parser.add_argument("--dry-run", action="store_true", help="Show detections without modifying files")
    parser.add_argument("--min-questions", type=int, default=5, help="Minimum questions for a session (default: 5)")
    parser.add_argument("--max-gap", type=float, default=30.0, help="Max minutes between consecutive questions (default: 30)")
    args = parser.parse_args()

    ext_dir = Path(__file__).parent.parent.parent / "data" / "extraction_output"
    total_detected = 0
    total_updated = 0

    for f in sorted(ext_dir.glob("????-??-??.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        sessions = detect_sessions(data, args.min_questions, args.max_gap)

        if sessions:
            for s in sessions:
                print(f"  {f.stem}: {s['quizmaster']} — {len(s['indices'])} Qs  theme={s['theme']}")
            total_detected += len(sessions)

            if not args.dry_run:
                count = apply_sessions(data, sessions, f.stem)
                f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                total_updated += count

    print(f"\n{total_detected} session(s) detected, {total_updated} question(s) updated.")
    if args.dry_run and total_detected:
        print("(dry run — no files modified)")


if __name__ == "__main__":
    main()

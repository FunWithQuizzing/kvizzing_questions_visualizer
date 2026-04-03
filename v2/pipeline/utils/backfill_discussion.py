"""
Backfill missing discussion entries for extracted questions.

For each extracted question, scans the original chat messages between the
question timestamp and the next question (or +15 min, whichever is sooner)
and adds any messages not already captured in the discussion array.

Messages from the question asker are classified as hint/confirmation;
messages from others are classified as attempt/chat based on heuristics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

log = logging.getLogger("kvizzing")

_MAX_DISCUSSION_WINDOW_S = 900  # 15 min max between question and end of its discussion


def backfill(
    questions_by_date: dict[str, list[dict]],
    messages_by_date: dict[str, list[dict]],
    dry_run: bool = False,
) -> dict[str, int]:
    """
    For each date's extracted questions, find chat messages that belong to each
    question's discussion but weren't captured by the LLM.

    Args:
        questions_by_date: {date_str: [extraction_output entries]}
        messages_by_date:  {date_str: [parsed chat messages]}
        dry_run: if True, log what would be added without modifying anything

    Returns:
        {date_str: count_of_new_entries_added}
    """
    results: dict[str, int] = {}

    for date_str in sorted(questions_by_date.keys()):
        qs = questions_by_date[date_str]
        msgs = messages_by_date.get(date_str, [])
        if not qs or not msgs:
            continue

        # Sort questions by timestamp
        qs_sorted = sorted(qs, key=lambda q: q.get("question_timestamp", ""))

        # Build a lookup of existing discussion timestamps per question
        added_count = 0

        for qi, q in enumerate(qs_sorted):
            q_ts_str = q.get("question_timestamp", "")
            if not q_ts_str:
                continue

            try:
                q_dt = datetime.fromisoformat(q_ts_str.rstrip("Z"))
            except Exception:
                continue

            q_asker = q.get("question_asker", "")

            # Window end: next question's timestamp or +15 min, whichever is sooner
            if qi + 1 < len(qs_sorted):
                next_ts = qs_sorted[qi + 1].get("question_timestamp", "")
                try:
                    next_dt = datetime.fromisoformat(next_ts.rstrip("Z"))
                except Exception:
                    next_dt = q_dt + timedelta(seconds=_MAX_DISCUSSION_WINDOW_S)
            else:
                next_dt = q_dt + timedelta(seconds=_MAX_DISCUSSION_WINDOW_S)

            # Cap at max window
            window_end = min(next_dt, q_dt + timedelta(seconds=_MAX_DISCUSSION_WINDOW_S))

            # Existing discussion timestamps (for dedup)
            discussion = q.get("discussion") or []
            existing_ts = set()
            for d in discussion:
                d_ts = d.get("timestamp", "")
                existing_ts.add(d_ts)

            # Scan chat messages in window
            new_entries = []
            for msg in msgs:
                msg_ts_str = msg["timestamp"]
                try:
                    msg_dt = datetime.fromisoformat(msg_ts_str.rstrip("Z"))
                except Exception:
                    continue

                # Must be after the question and before window end
                if msg_dt <= q_dt or msg_dt >= window_end:
                    continue

                # Skip if already in discussion
                if msg_ts_str in existing_ts:
                    continue

                # Skip the question message itself
                if msg_ts_str == q_ts_str:
                    continue

                # Skip system messages, empty messages
                text = msg.get("text", "").strip()
                if not text or msg.get("username", "") == "system":
                    continue

                # Classify role
                username = msg["username"]
                if username == q_asker:
                    # Asker replying — could be hint or confirmation
                    text_lower = text.lower()
                    if any(w in text_lower for w in ["correct", "yes!", "right", "ding", "bingo", "got it", "well done"]):
                        role = "confirmation"
                    else:
                        role = "hint"
                else:
                    role = "attempt"

                new_entries.append({
                    "timestamp": msg_ts_str,
                    "username": username,
                    "text": text,
                    "role": role,
                    "is_correct": None,
                    "has_media": bool(msg.get("has_media")),
                })

            if new_entries:
                if dry_run:
                    log.info(
                        "  [%s] Q [%s] %s: would add %d discussion entries",
                        date_str, q_ts_str[11:19], q_asker, len(new_entries),
                    )
                    for e in new_entries[:3]:
                        log.info("    + [%s] %s: %s", e["timestamp"][11:19], e["username"], e["text"][:80])
                    if len(new_entries) > 3:
                        log.info("    ... and %d more", len(new_entries) - 3)
                else:
                    # Append and re-sort by timestamp
                    discussion.extend(new_entries)
                    discussion.sort(key=lambda d: d.get("timestamp", ""))
                    q["discussion"] = discussion

                added_count += len(new_entries)

        if added_count > 0:
            results[date_str] = added_count

    return results

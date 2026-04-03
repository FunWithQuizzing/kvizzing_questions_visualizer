"""
Media file → question/discussion matching.

Scans a WhatsApp export directory for media files and matches them to:
  - questions (where question.has_media=True) by timestamp proximity
  - discussion entries (where has_media=True and role is hint/answer_reveal)

Filename format:  00000050-PHOTO-2025-09-23-14-58-50.jpg
                  <seq>-<TYPE>-<YYYY>-<MM>-<DD>-<HH>-<MM>-<SS>.<ext>

The filename timestamp is in the exporter's local timezone. In practice
the filename time runs ~39 s before the chat message timestamp (file
creation vs. send time). The match window in pipeline_config.json covers
this offset plus slack for images posted mid-thread (rather than inline
with the question text), which can add another 1–2 minutes.

Matching uses a two-pass global-optimal greedy strategy:
  Pass 1: question-level media (same algorithm as before)
  Pass 2: discussion-level media (hint + answer_reveal) using remaining files

Multi-image posts (multiple files landing within 2 s of the primary match)
are all attached to the same target.
"""

from __future__ import annotations

import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

log = logging.getLogger("kvizzing")

# ── Perceptual deduplication ──────────────────────────────────────────────────
# Uses imagehash (pHash) to drop near-duplicate images from the same burst.
# Falls back gracefully if Pillow / imagehash are not installed.
_PHASH_THRESHOLD = 8  # Hamming distance ≤ 8/64 bits → near-duplicate

try:
    import imagehash
    from PIL import Image as _PILImage
    _PHASH_AVAILABLE = True
except ImportError:
    _PHASH_AVAILABLE = False


def _dedup_images(
    files: list[tuple[str, str]],   # [(media_type, filename), ...]
    media_dir: Path,
) -> list[tuple[str, str]]:
    """
    Remove near-duplicate images from a list of (media_type, filename) tuples.

    Only image-type entries are deduplicated; video/audio pass through unchanged.
    The first occurrence of each unique image is kept (primary file first).
    Requires imagehash + Pillow; if unavailable, returns the list unchanged.
    """
    if not _PHASH_AVAILABLE or len(files) <= 1:
        return files

    seen_hashes: list = []
    kept: list[tuple[str, str]] = []
    dropped = 0

    for media_type, filename in files:
        if media_type != "image":
            kept.append((media_type, filename))
            continue
        path = media_dir / filename
        try:
            h = imagehash.phash(_PILImage.open(path))
        except Exception:
            kept.append((media_type, filename))
            continue

        is_dup = any(abs(h - prev) <= _PHASH_THRESHOLD for prev in seen_hashes)
        if is_dup:
            dropped += 1
            log.debug("  Dedup: dropped near-duplicate %s", filename)
        else:
            seen_hashes.append(h)
            kept.append((media_type, filename))

    if dropped:
        log.info("  Dedup: removed %d near-duplicate image(s)", dropped)
    return kept

# ── Filename parsing ──────────────────────────────────────────────────────────

_FILENAME_RE = re.compile(
    r"^(\d+)-(PHOTO|VIDEO|GIF|STICKER|AUDIO)-"
    r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})"
    r"\.(jpg|jpeg|png|webp|mp4|mov|opus|mp3|pdf|webm)$",
    re.IGNORECASE,
)

_TYPE_MAP: dict[str, str] = {
    "PHOTO":   "image",
    "STICKER": "image",
    "VIDEO":   "video",
    "GIF":     "video",
    "AUDIO":   "audio",
}


def _parse_filename(name: str) -> tuple[int, str, datetime] | None:
    """Returns (seq, media_type_str, local_datetime) or None."""
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    seq = int(m.group(1))
    raw_type = m.group(2).upper()
    year, month, day = int(m.group(3)), int(m.group(4)), int(m.group(5))
    hour, minute, second = int(m.group(6)), int(m.group(7)), int(m.group(8))
    return seq, _TYPE_MAP.get(raw_type, "image"), datetime(year, month, day, hour, minute, second)


# ── Main matching function ────────────────────────────────────────────────────

_DISCUSSION_MEDIA_ROLES = frozenset({"answer_reveal", "hint"})


def match_media(questions: list, media_dir: Path, config: dict) -> list:
    """
    Match media files to questions and discussion entries.

    Pass 1: questions where question.has_media=True and question.media is None.
    Pass 2: discussion entries where has_media=True, media is None, and role is
            hint or answer_reveal. Uses files not consumed by pass 1.

    Args:
        questions:  list of KVizzingQuestion objects
        media_dir:  directory containing WhatsApp export media files
        config:     pipeline_config dict

    Returns:
        New list of KVizzingQuestion objects with question.media[] and/or
        discussion[].media[] populated (filename + type; url=None until CDN upload).
        All other questions are returned unchanged.
    """
    from zoneinfo import ZoneInfo

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))
    from schema import MediaAttachment, MediaType

    source_tz = ZoneInfo(config["source_timezone"])
    window_s: int = config.get("media_enrichment", {}).get("match_window_seconds", 90)

    # ── 1. Index all media files ──────────────────────────────────────────────
    media_files: list[tuple[int, str, datetime, str]] = []  # (seq, type, local_dt, filename)
    for path in sorted(media_dir.iterdir()):
        parsed = _parse_filename(path.name)
        if parsed is None:
            continue
        seq, media_type, local_dt = parsed
        media_files.append((seq, media_type, local_dt, path.name))

    media_files.sort(key=lambda f: (f[2], f[0]))
    log.info("  Found %d matchable media files in %s", len(media_files), media_dir)

    if not media_files:
        log.warning("  No media files found — check --media-dir path.")
        return questions

    # ── 2. Separate questions that still need matching ────────────────────────
    needs_match: list = []
    skipped_already_set = 0

    for q in questions:
        if q.question.has_media and q.question.media is None:
            needs_match.append(q)
        elif q.question.has_media and q.question.media is not None:
            skipped_already_set += 1

    has_media_total = sum(1 for q in questions if q.question.has_media)

    # ── 3. Build & sort all valid (question, file) pairs by |delta| ───────────
    # Global-optimal greedy: smallest-delta pairs get priority, so each file
    # always goes to its true nearest question regardless of processing order.
    q_local_map: dict[str, datetime] = {}
    for q in needs_match:
        q_local_map[q.id] = (
            q.question.timestamp
            .replace(tzinfo=ZoneInfo("UTC"))
            .astimezone(source_tz)
            .replace(tzinfo=None)
        )

    pairs: list[tuple[float, int, str, str, str, datetime]] = []
    # (abs_delta, seq, q_id, media_type, filename, file_dt)
    for seq, media_type, file_dt, filename in media_files:
        for q in needs_match:
            q_local = q_local_map[q.id]
            delta = abs((file_dt - q_local).total_seconds())
            if delta <= window_s:
                pairs.append((delta, seq, q.id, media_type, filename, file_dt))

    # Sort by absolute delta (ascending), then seq (tie-break: prefer earlier file)
    pairs.sort(key=lambda p: (p[0], p[1]))

    # ── 4. Greedy 1:1 primary assignment ─────────────────────────────────────
    used_files: set[str] = set()
    assigned_q: set[str] = set()
    primary_assignment: dict[str, tuple[str, str, datetime]] = {}
    # q_id → (media_type, filename, file_dt)

    for abs_delta, seq, q_id, media_type, filename, file_dt in pairs:
        if q_id in assigned_q or filename in used_files:
            continue
        primary_assignment[q_id] = (media_type, filename, file_dt)
        assigned_q.add(q_id)
        used_files.add(filename)

    # ── 5. Multi-image extension ──────────────────────────────────────────────
    # For each assigned question, attach additional files that land within 2 s
    # of the primary file (same-second multi-image posts).
    extra_files: dict[str, list[tuple[str, str]]] = defaultdict(list)
    # q_id → [(media_type, filename), ...]

    for q_id, (_, _, primary_dt) in primary_assignment.items():
        for seq, media_type, file_dt, filename in media_files:
            if filename in used_files:
                continue
            if abs((file_dt - primary_dt).total_seconds()) <= 2:
                extra_files[q_id].append((media_type, filename))
                used_files.add(filename)

    # ── 6. Build updated question objects ─────────────────────────────────────
    q_by_id = {q.id: q for q in needs_match}
    matched_count = 0
    updated_by_id: dict[str, object] = {}

    for q_id, (primary_type, primary_filename, primary_dt) in primary_assignment.items():
        q = q_by_id[q_id]
        q_local = q_local_map[q_id]

        all_files = [(primary_type, primary_filename)] + extra_files.get(q_id, [])
        all_files = _dedup_images(all_files, media_dir)
        attachments: list[MediaAttachment] = []
        for media_type_str, filename in all_files:
            try:
                mt = MediaType(media_type_str)
            except ValueError:
                mt = MediaType.image
            attachments.append(MediaAttachment(type=mt, url=None, filename=filename, caption=None))

        new_q = q.question.model_copy(update={"media": attachments})
        updated_by_id[q_id] = q.model_copy(update={"question": new_q})
        matched_count += 1

        delta_signed = (primary_dt - q_local).total_seconds()
        log.debug(
            "  [%s] Matched %d file(s): %s  (Δt=%+.0fs)",
            q_id, len(all_files), [f for _, f in all_files], delta_signed,
        )

    # ── 7. Assemble final list (preserve original order) ─────────────────────
    updated: list = []
    for q in questions:
        if q.id in updated_by_id:
            updated.append(updated_by_id[q.id])
        else:
            updated.append(q)

    log.info(
        "  Pass 1 (questions): %d/%d has_media questions matched  (%d already had media set)",
        matched_count, has_media_total, skipped_already_set,
    )

    unmatched = has_media_total - matched_count - skipped_already_set
    if unmatched:
        log.warning(
            "  %d has_media questions unmatched — "
            "their media files were not included in the export "
            "or fell outside the %ds window (tune media_enrichment.match_window_seconds "
            "in pipeline_config.json).",
            unmatched, window_s,
        )

    # ── Pass 2: match remaining files to discussion entries ───────────────────
    # Targets: hint and answer_reveal entries with has_media=True and media=None.
    disc_targets: list[tuple[str, int, datetime]] = []  # (q_id, d_idx, local_dt)
    for q in updated:
        for d_idx, d in enumerate(q.discussion or []):
            if (d.has_media and d.media is None
                    and d.role.value in _DISCUSSION_MEDIA_ROLES):
                d_local = (
                    d.timestamp
                    .replace(tzinfo=ZoneInfo("UTC"))
                    .astimezone(source_tz)
                    .replace(tzinfo=None)
                )
                disc_targets.append((q.id, d_idx, d_local))

    if disc_targets:
        remaining_files = [(s, t, dt, fn) for s, t, dt, fn in media_files if fn not in used_files]

        # Build pairs
        disc_pairs: list[tuple] = []
        for seq, media_type, file_dt, filename in remaining_files:
            for q_id, d_idx, d_local in disc_targets:
                delta = abs((file_dt - d_local).total_seconds())
                if delta <= window_s:
                    disc_pairs.append((delta, seq, q_id, d_idx, media_type, filename, file_dt))

        disc_pairs.sort(key=lambda p: (p[0], p[1]))

        # Greedy 1:1 assignment
        disc_used: set[str] = set()
        disc_assigned: set[tuple] = set()  # (q_id, d_idx)
        disc_primary: dict[tuple, tuple] = {}  # (q_id, d_idx) → (media_type, filename, file_dt)

        for abs_delta, seq, q_id, d_idx, media_type, filename, file_dt in disc_pairs:
            key = (q_id, d_idx)
            if key in disc_assigned or filename in disc_used:
                continue
            disc_primary[key] = (media_type, filename, file_dt)
            disc_assigned.add(key)
            disc_used.add(filename)

        # Multi-image extension
        disc_extra: dict[tuple, list[tuple[str, str]]] = defaultdict(list)
        for key, (_, _, primary_dt) in disc_primary.items():
            for seq, media_type, file_dt, filename in remaining_files:
                if filename in disc_used:
                    continue
                if abs((file_dt - primary_dt).total_seconds()) <= 2:
                    disc_extra[key].append((media_type, filename))
                    disc_used.add(filename)

        # Apply matches back to questions
        by_q: dict[str, dict[int, list[tuple[str, str]]]] = defaultdict(dict)
        for (q_id, d_idx), (primary_type, primary_filename, _) in disc_primary.items():
            all_files = [(primary_type, primary_filename)] + disc_extra.get((q_id, d_idx), [])
            all_files = _dedup_images(all_files, media_dir)
            by_q[q_id][d_idx] = all_files

        updated2: list = []
        for q in updated:
            if q.id not in by_q:
                updated2.append(q)
                continue

            d_matches = by_q[q.id]
            new_discussion = list(q.discussion or [])
            for d_idx, all_files in d_matches.items():
                if d_idx >= len(new_discussion):
                    continue
                attachments: list[MediaAttachment] = []
                for media_type_str, filename in all_files:
                    try:
                        mt = MediaType(media_type_str)
                    except ValueError:
                        mt = MediaType.image
                    attachments.append(MediaAttachment(type=mt, url=None, filename=filename, caption=None))
                new_discussion[d_idx] = new_discussion[d_idx].model_copy(update={"media": attachments})
                log.debug(
                    "  [%s] discussion[%d] matched %d file(s): %s",
                    q.id, d_idx, len(all_files), [f for _, f in all_files],
                )
            updated2.append(q.model_copy(update={"discussion": new_discussion}))

        updated = updated2
        disc_matched = len(disc_primary)
        disc_total = len(disc_targets)
        disc_unmatched = disc_total - disc_matched
        log.info(
            "  Pass 2 (discussion): %d/%d hint/answer_reveal entries matched",
            disc_matched, disc_total,
        )
        if disc_unmatched:
            log.warning(
                "  %d discussion entries unmatched — files not in export or outside %ds window.",
                disc_unmatched, window_s,
            )

    return updated

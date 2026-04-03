"""
Cloudflare R2 upload utility.

Reads questions from the DB where media[].filename is set but url is null,
uploads the files to R2, then writes the public URL back to the DB.

Required env vars:
    R2_ACCOUNT_ID         Cloudflare account ID
    R2_ACCESS_KEY_ID      R2 API token access key
    R2_SECRET_ACCESS_KEY  R2 API token secret key
    R2_BUCKET             Bucket name (e.g. "kvizzing-media")
    R2_PUBLIC_URL         Public base URL (e.g. "https://pub-xxx.r2.dev"
                          or a custom domain "https://media.yourdomain.com")

Install:
    pip install boto3
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

log = logging.getLogger("kvizzing")

_CONTENT_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".webm": "video/webm",
    ".opus": "audio/opus",
    ".mp3":  "audio/mpeg",
    ".pdf":  "application/pdf",
}


def _get_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


def _make_client():
    """Build a boto3 S3 client pointed at Cloudflare R2."""
    try:
        import boto3
    except ImportError:
        raise RuntimeError("boto3 required: pip install boto3")

    account_id        = os.environ.get("R2_ACCOUNT_ID")
    access_key_id     = os.environ.get("R2_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")

    missing = [v for v, k in [
        (account_id, "R2_ACCOUNT_ID"),
        (access_key_id, "R2_ACCESS_KEY_ID"),
        (secret_access_key, "R2_SECRET_ACCESS_KEY"),
    ] if not v]
    if missing:
        raise RuntimeError(
            f"Missing env vars: {', '.join(missing)}. "
            "Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY."
        )

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )


def upload_media(questions: list, media_dir: Path, dry_run: bool = False) -> list:
    """
    For each question with media[].filename set and url=None, upload the file
    to R2 and populate url.

    Args:
        questions:  list of KVizzingQuestion objects (all questions)
        media_dir:  directory containing the local media files
        dry_run:    if True, log what would be uploaded without actually uploading

    Returns:
        Updated question list (questions with newly-set URLs are new objects;
        others are the same objects).
    """
    bucket      = os.environ.get("R2_BUCKET")
    public_base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")

    if not bucket:
        raise RuntimeError("Set R2_BUCKET env var (e.g. 'kvizzing-media').")
    if not public_base:
        raise RuntimeError(
            "Set R2_PUBLIC_URL env var (e.g. 'https://pub-xxx.r2.dev' "
            "or your custom domain)."
        )

    client = None if dry_run else _make_client()

    # Collect unique filenames that need uploading (url currently null)
    # Covers both question-level and discussion-level (hint/answer_reveal) media.
    to_upload: dict[str, Path] = {}  # filename → local path
    for q in questions:
        for att in q.question.media or []:
            if att.filename and att.url is None:
                local = media_dir / att.filename
                if local.exists():
                    to_upload[att.filename] = local
                else:
                    log.warning("  File not found locally, skipping: %s", att.filename)
        for d in q.discussion or []:
            for att in d.media or []:
                if att.filename and att.url is None:
                    local = media_dir / att.filename
                    if local.exists():
                        to_upload[att.filename] = local
                    else:
                        log.warning("  File not found locally, skipping: %s", att.filename)

    log.info("  %d unique file(s) to upload to R2 bucket '%s'", len(to_upload), bucket)

    if dry_run:
        for filename in sorted(to_upload):
            log.info("  [dry-run] Would upload: %s", filename)
        return questions

    # Upload and track which filenames now have a URL
    uploaded_urls: dict[str, str] = {}
    for filename, local_path in to_upload.items():
        content_type = _get_content_type(filename)
        try:
            client.upload_file(
                str(local_path),
                bucket,
                filename,
                ExtraArgs={"ContentType": content_type},
            )
            url = f"{public_base}/{filename}"
            uploaded_urls[filename] = url
            log.debug("  Uploaded: %s → %s", filename, url)
        except Exception as e:
            log.error("  Failed to upload %s: %s", filename, e)

    log.info("  Uploaded %d/%d files successfully.", len(uploaded_urls), len(to_upload))

    if not uploaded_urls:
        return questions

    # Patch url fields in question objects (question media + discussion media)
    updated = []
    changed = 0
    for q in questions:
        modified = False

        # Patch question-level media
        new_q_media = q.question.media
        if q.question.media:
            patched = [
                att.model_copy(update={"url": uploaded_urls[att.filename]})
                if att.filename and att.filename in uploaded_urls and att.url is None
                else att
                for att in q.question.media
            ]
            if patched != q.question.media:
                new_q_media = patched
                modified = True

        # Patch discussion-level media
        new_discussion = q.discussion
        if q.discussion:
            new_entries = []
            disc_modified = False
            for d in q.discussion:
                if d.media:
                    patched_d = [
                        att.model_copy(update={"url": uploaded_urls[att.filename]})
                        if att.filename and att.filename in uploaded_urls and att.url is None
                        else att
                        for att in d.media
                    ]
                    if patched_d != d.media:
                        new_entries.append(d.model_copy(update={"media": patched_d}))
                        disc_modified = True
                        modified = True
                    else:
                        new_entries.append(d)
                else:
                    new_entries.append(d)
            if disc_modified:
                new_discussion = new_entries

        if modified:
            updates: dict = {}
            if new_q_media is not q.question.media:
                updates["question"] = q.question.model_copy(update={"media": new_q_media})
            if new_discussion is not q.discussion:
                updates["discussion"] = new_discussion
            updated.append(q.model_copy(update=updates))
            changed += 1
        else:
            updated.append(q)

    log.info("  Updated url on %d questions.", changed)
    return updated

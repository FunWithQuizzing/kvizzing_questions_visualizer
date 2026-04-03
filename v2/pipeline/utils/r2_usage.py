"""
Cloudflare R2 free-tier usage checker.

Free tier limits (as of 2025):
    Storage:          10 GB / month
    Class A ops:       1 million / month  (PUT, POST, LIST, COPY, DELETE)
    Class B ops:      10 million / month  (GET, HEAD)

Storage is measured via boto3 list_objects (one Class A LIST op per 1000 objects).
Operation counts are fetched from the Cloudflare GraphQL Analytics API.

Required env vars:
    R2_ACCOUNT_ID         Cloudflare account ID
    R2_ACCESS_KEY_ID      R2 API token access key
    R2_SECRET_ACCESS_KEY  R2 API token secret key
    R2_BUCKET             Bucket name

Optional (for operation count checks):
    CLOUDFLARE_API_TOKEN  API token with "Account Analytics:Read" permission
                          (create at dash.cloudflare.com → My Profile → API Tokens)
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

log = logging.getLogger("kvizzing")

# ── Free tier limits ──────────────────────────────────────────────────────────

FREE_STORAGE_BYTES   = 10 * 1024 ** 3   # 10 GB
FREE_CLASS_A_OPS     = 1_000_000
FREE_CLASS_B_OPS     = 10_000_000

# Warn when usage reaches this fraction of the free limit
_WARN_THRESHOLD = 0.80

# Class A operations (writes): PUT, COPY, LIST, DELETE, POST
_CLASS_A_ACTIONS = {"PutObject", "CopyObject", "CreateMultipartUpload",
                    "UploadPart", "CompleteMultipartUpload", "DeleteObject",
                    "DeleteObjects", "ListObjectsV2", "ListObjects",
                    "ListMultipartUploads", "ListParts", "AbortMultipartUpload",
                    "PutBucketCors", "PutBucketLifecycleConfiguration"}

# Class B operations (reads): GET, HEAD
_CLASS_B_ACTIONS = {"GetObject", "HeadObject", "HeadBucket", "GetBucketLocation",
                    "GetBucketCors", "GetBucketLifecycleConfiguration"}


# ── Storage check via boto3 ───────────────────────────────────────────────────

def _check_storage(client, bucket: str) -> int:
    """
    Return total storage bytes in the bucket.
    Uses paginated list_objects_v2 — each page is 1 Class A op.
    """
    total_bytes = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            total_bytes += obj.get("Size", 0)
    return total_bytes


# ── Operation count via Cloudflare GraphQL API ────────────────────────────────

_GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

_OPS_QUERY = """
query R2Ops($accountId: String!, $startDate: Date!, $endDate: Date!, $bucket: String!) {
  viewer {
    accounts(filter: {accountTag: $accountId}) {
      r2OperationsAdaptiveGroups(
        filter: {
          date_geq: $startDate
          date_leq: $endDate
          bucketName: $bucket
        }
        limit: 10000
        orderBy: [date_ASC]
      ) {
        sum { requests }
        dimensions { actionType }
      }
    }
  }
}
"""


def _check_operations(account_id: str, bucket: str, cf_token: str) -> tuple[int, int]:
    """
    Return (class_a_ops, class_b_ops) for the current calendar month.
    Requires a Cloudflare API token with Account Analytics:Read permission.
    """
    try:
        import urllib.request, urllib.error, json as _json
    except ImportError:
        return 0, 0

    today = date.today()
    start = today.replace(day=1).isoformat()
    end   = today.isoformat()

    payload = _json.dumps({
        "query": _OPS_QUERY,
        "variables": {
            "accountId": account_id,
            "startDate": start,
            "endDate":   end,
            "bucket":    bucket,
        },
    }).encode()

    req = urllib.request.Request(
        _GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {cf_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
    except Exception as e:
        log.warning("  Could not fetch R2 operation counts from Cloudflare API: %s", e)
        return 0, 0

    class_a = 0
    class_b = 0
    try:
        groups = (
            data["data"]["viewer"]["accounts"][0]
            ["r2OperationsAdaptiveGroups"]
        )
        for g in groups:
            action = g["dimensions"]["actionType"]
            count  = g["sum"]["requests"]
            if action in _CLASS_A_ACTIONS:
                class_a += count
            elif action in _CLASS_B_ACTIONS:
                class_b += count
    except (KeyError, IndexError, TypeError) as e:
        log.warning("  Unexpected Cloudflare API response shape: %s", e)

    return class_a, class_b


# ── Public entry point ────────────────────────────────────────────────────────

def write_usage_json(result: dict, output_path: "Path") -> None:
    """
    Write r2_usage.json to output_path so the visualizer can display alerts.

    The file is always written (even if warnings is empty) so the UI has
    a "checked_at" timestamp showing when the data is fresh.
    """
    import json
    from datetime import datetime, timezone

    payload = {
        "checked_at":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "storage_bytes": result.get("storage_bytes", 0),
        "storage_pct":   round(result.get("storage_bytes", 0) / FREE_STORAGE_BYTES * 100, 1),
        "class_a_ops":   result.get("class_a_ops", 0),
        "class_a_pct":   round(result.get("class_a_ops", 0) / FREE_CLASS_A_OPS * 100, 1),
        "class_b_ops":   result.get("class_b_ops", 0),
        "class_b_pct":   round(result.get("class_b_ops", 0) / FREE_CLASS_B_OPS * 100, 1),
        "warnings":      result.get("warnings", []),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    log.info("  Wrote R2 usage to %s", output_path)


def check_and_warn(client=None, output_path: "Path | None" = None) -> dict:
    """
    Check current R2 usage against free-tier limits and log warnings.

    Args:
        client:      an existing boto3 S3 client. If None, one is created from env vars.
        output_path: if given, write r2_usage.json there for the UI to consume.

    Returns:
        dict with keys: storage_bytes, class_a_ops, class_b_ops, warnings (list[str])
    """
    account_id        = os.environ.get("R2_ACCOUNT_ID", "")
    access_key_id     = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    bucket            = os.environ.get("R2_BUCKET", "")
    cf_token          = os.environ.get("CLOUDFLARE_API_TOKEN", "")

    if not all([account_id, access_key_id, secret_access_key, bucket]):
        log.warning("  Skipping R2 usage check — missing env vars.")
        return {}

    if client is None:
        try:
            import boto3
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
            )
        except ImportError:
            log.warning("  boto3 not installed — skipping R2 usage check.")
            return {}

    warnings: list[str] = []

    # ── Storage ───────────────────────────────────────────────────────────────
    try:
        storage_bytes = _check_storage(client, bucket)
        storage_gb    = storage_bytes / 1024 ** 3
        storage_pct   = storage_bytes / FREE_STORAGE_BYTES
        log.info("  Storage:     %.2f GB / 10 GB  (%.0f%%)", storage_gb, storage_pct * 100)
        if storage_pct >= _WARN_THRESHOLD:
            msg = (
                f"R2 storage at {storage_pct:.0%} of free limit "
                f"({storage_gb:.2f} GB / 10 GB). "
                "You will be charged $0.015/GB-month beyond 10 GB."
            )
            warnings.append(msg)
            log.warning("  ⚠  %s", msg)
    except Exception as e:
        log.warning("  Could not check R2 storage: %s", e)
        storage_bytes = 0

    # ── Operations ────────────────────────────────────────────────────────────
    class_a_ops = class_b_ops = 0
    if cf_token:
        class_a_ops, class_b_ops = _check_operations(account_id, bucket, cf_token)

        a_pct = class_a_ops / FREE_CLASS_A_OPS
        b_pct = class_b_ops / FREE_CLASS_B_OPS
        log.info(
            "  Class A ops: %s / 1,000,000  (%.0f%%)",
            f"{class_a_ops:,}", a_pct * 100,
        )
        log.info(
            "  Class B ops: %s / 10,000,000  (%.0f%%)",
            f"{class_b_ops:,}", b_pct * 100,
        )

        if a_pct >= _WARN_THRESHOLD:
            msg = (
                f"R2 Class A operations at {a_pct:.0%} of free limit "
                f"({class_a_ops:,} / 1,000,000). "
                "You will be charged $4.50/million beyond the limit."
            )
            warnings.append(msg)
            log.warning("  ⚠  %s", msg)

        if b_pct >= _WARN_THRESHOLD:
            msg = (
                f"R2 Class B operations at {b_pct:.0%} of free limit "
                f"({class_b_ops:,} / 10,000,000). "
                "You will be charged $0.36/million beyond the limit."
            )
            warnings.append(msg)
            log.warning("  ⚠  %s", msg)
    else:
        log.info(
            "  Class A/B ops: not checked "
            "(set CLOUDFLARE_API_TOKEN with Account Analytics:Read to enable)"
        )

    if not warnings:
        log.info("  R2 usage is within free-tier limits.")

    result = {
        "storage_bytes": storage_bytes,
        "class_a_ops":   class_a_ops,
        "class_b_ops":   class_b_ops,
        "warnings":      warnings,
    }

    if output_path is not None:
        write_usage_json(result, output_path)

    return result

"""
Campaign fetcher service.

Fetches raw campaign insights from the Facebook Ads API and stores them
in S3.  All AWS credentials are resolved via the standard boto3 credential
chain; the Facebook access token is retrieved from AWS Secrets Manager.
"""

import json
import logging
import os
import time

import boto3

from backend.integrations.fb_client import FacebookAPIError, get_insights

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (resolved from environment variables with sensible defaults)
# ---------------------------------------------------------------------------

FB_SECRET_NAME = os.environ.get("FB_SECRET_NAME", "facebook/access_token")
RAW_BUCKET = os.environ.get("RAW_BUCKET", "raw-bucket")
ADMIN_SNS_TOPIC_ARN = os.environ.get("ADMIN_SNS_TOPIC_ARN", "")

FIELDS = (
    "campaign_id,campaign_name,impressions,clicks,spend,"
    "conversions,reach,frequency,date_start,date_stop"
)

MAX_RETRIES = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_access_token() -> str:
    """Retrieve the Facebook access token from AWS Secrets Manager."""
    client = boto3.client("secretsmanager")
    return client.get_secret_value(SecretId=FB_SECRET_NAME)["SecretString"]


def _publish_token_expiry_alert(account_id: str, error: FacebookAPIError) -> None:
    """Publish an SNS alert to the admin topic when the FB token has expired."""
    if not ADMIN_SNS_TOPIC_ARN:
        logger.error(
            "ADMIN_SNS_TOPIC_ARN is not set; cannot publish token-expiry alert."
        )
        return

    client = boto3.client("sns")
    message = (
        f"Facebook access token has expired for account '{account_id}'. "
        f"API returned HTTP {error.status_code}: {error.message}. "
        "Please refresh the token in AWS Secrets Manager."
    )
    client.publish(
        TopicArn=ADMIN_SNS_TOPIC_ARN,
        Subject="[ALERT] Facebook Access Token Expired",
        Message=message,
    )
    logger.warning("Token-expiry SNS alert published for account %s.", account_id)


def _write_to_s3(bucket: str, key: str, data: bytes) -> None:
    """Write *data* to S3 with SSE-S3 encryption."""
    client = boto3.client("s3")
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ServerSideEncryption="AES256",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_and_store(account_id: str, date_range: dict) -> str:
    """Fetch all campaign insights for *account_id* and persist them to S3.

    Follows all pagination cursors until no next page exists, accumulating
    every record.  The consolidated payload is written to S3 as a single
    JSON object with SSE-S3 encryption.

    Retry behaviour:
    - HTTP 429 (rate-limit): exponential backoff, up to ``MAX_RETRIES`` (5)
      attempts.  After exhausting retries the exception is re-raised so the
      caller (Lambda) can route the event to the configured DLQ.
    - HTTP 401 (token expired): an SNS alert is published to the admin topic
      and the exception is re-raised immediately (no retries).

    Args:
        account_id: Facebook ad account ID, e.g. ``"act_123456789"``.
        date_range: Dict with ``"since"`` and ``"until"`` keys
                    (``"YYYY-MM-DD"`` strings).

    Returns:
        The S3 key of the written object, e.g.
        ``"raw/2024-01-15/act_123456789.json"``.

    Raises:
        FacebookAPIError: On token expiry (401) or after exhausting retries
                          on rate-limit (429).
    """
    access_token = _get_access_token()

    all_records: list[dict] = []
    cursor: str | None = None

    # -----------------------------------------------------------------------
    # Pagination loop — accumulate all pages
    # -----------------------------------------------------------------------
    while True:
        response = _get_insights_with_retry(
            account_id=account_id,
            date_range=date_range,
            access_token=access_token,
            cursor=cursor,
        )

        page_data: list[dict] = response.get("data", [])
        all_records.extend(page_data)

        # Check for a next page
        paging = response.get("paging", {})
        if "next" not in paging:
            break

        cursor = paging.get("cursors", {}).get("after")
        if cursor is None:
            # Defensive: no cursor means we cannot advance — stop.
            break

    # -----------------------------------------------------------------------
    # Persist to S3
    # -----------------------------------------------------------------------
    date_str = date_range["since"]
    s3_key = f"raw/{date_str}/{account_id}.json"

    payload = json.dumps(all_records, default=str).encode("utf-8")
    _write_to_s3(RAW_BUCKET, s3_key, payload)

    logger.info(
        "Stored %d records for account %s to s3://%s/%s",
        len(all_records),
        account_id,
        RAW_BUCKET,
        s3_key,
    )
    return s3_key


# ---------------------------------------------------------------------------
# Internal retry wrapper
# ---------------------------------------------------------------------------


def _get_insights_with_retry(
    account_id: str,
    date_range: dict,
    access_token: str,
    cursor: str | None,
) -> dict:
    """Call ``get_insights`` with exponential backoff on HTTP 429.

    Raises:
        FacebookAPIError: Immediately on 401; after ``MAX_RETRIES`` on 429.
    """
    for attempt in range(MAX_RETRIES):
        try:
            return get_insights(
                account_id=account_id,
                date_range=date_range,
                access_token=access_token,
                fields=FIELDS,
                after=cursor,
            )
        except FacebookAPIError as exc:
            if exc.status_code == 401:
                # Token expired — alert admin and halt immediately.
                _publish_token_expiry_alert(account_id, exc)
                raise

            if exc.status_code == 429:
                if attempt < MAX_RETRIES - 1:
                    sleep_seconds = 2 ** attempt
                    logger.warning(
                        "Rate-limited (429) on attempt %d/%d for account %s. "
                        "Retrying in %ds.",
                        attempt + 1,
                        MAX_RETRIES,
                        account_id,
                        sleep_seconds,
                    )
                    time.sleep(sleep_seconds)
                    continue
                else:
                    # Exhausted retries — re-raise so Lambda routes to DLQ.
                    logger.error(
                        "Exhausted %d retries for account %s. Routing to DLQ.",
                        MAX_RETRIES,
                        account_id,
                    )
                    raise

            # Any other error — propagate immediately.
            raise

    # Should be unreachable, but satisfies type checkers.
    raise RuntimeError("Unexpected exit from retry loop")  # pragma: no cover

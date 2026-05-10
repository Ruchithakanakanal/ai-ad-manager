"""
Unit tests for backend/services/campaign_fetcher.py

Covers:
- fetch_and_store: single-page success, multi-page pagination, rate-limit retry,
  rate-limit exhausted (DLQ routing), token expiry SNS alert

Requirements: 2.5, 2.6
"""

import json
import os
import pytest
import boto3
from unittest.mock import patch, MagicMock, call

from moto import mock_aws

from backend.integrations.fb_client import FacebookAPIError
import backend.services.campaign_fetcher as fetcher_module

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNT_ID = "act_123456789"
DATE_RANGE = {"since": "2024-01-15", "until": "2024-01-31"}
EXPECTED_S3_KEY = f"raw/{DATE_RANGE['since']}/{ACCOUNT_ID}.json"
RAW_BUCKET = "raw-bucket"

SAMPLE_RECORD_1 = {
    "campaign_id": "camp_001",
    "campaign_name": "Summer Sale",
    "impressions": "10000",
    "clicks": "500",
    "spend": "250.00",
    "date_start": "2024-01-15",
    "date_stop": "2024-01-31",
}

SAMPLE_RECORD_2 = {
    "campaign_id": "camp_002",
    "campaign_name": "Winter Promo",
    "impressions": "8000",
    "clicks": "320",
    "spend": "180.00",
    "date_start": "2024-01-15",
    "date_stop": "2024-01-31",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _single_page_response(records: list) -> dict:
    """Build a Facebook API response with no next page."""
    return {
        "data": records,
        "paging": {
            "cursors": {"before": "cursor_before", "after": "cursor_after"},
            # No "next" key → last page
        },
    }


def _page_with_next(records: list, after_cursor: str) -> dict:
    """Build a Facebook API response that has a next page."""
    return {
        "data": records,
        "paging": {
            "cursors": {"before": "cursor_before", "after": after_cursor},
            "next": f"https://graph.facebook.com/v18.0/{ACCOUNT_ID}/insights?after={after_cursor}",
        },
    }


def _create_s3_bucket(region: str = "us-east-1") -> None:
    """Create the raw S3 bucket inside a moto context."""
    s3 = boto3.client("s3", region_name=region)
    s3.create_bucket(Bucket=RAW_BUCKET)


# ---------------------------------------------------------------------------
# Test: single-page success
# ---------------------------------------------------------------------------


@mock_aws
def test_fetch_and_store_success_single_page():
    """Returns correct S3 key; S3 object exists with correct content."""
    _create_s3_bucket()

    response_body = _single_page_response([SAMPLE_RECORD_1])

    with (
        patch.object(fetcher_module, "_get_access_token", return_value="test_token"),
        patch.object(fetcher_module, "get_insights", return_value=response_body),
        patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
    ):
        result = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

    assert result == EXPECTED_S3_KEY

    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket=RAW_BUCKET, Key=EXPECTED_S3_KEY)
    stored_data = json.loads(obj["Body"].read().decode("utf-8"))
    assert stored_data == [SAMPLE_RECORD_1]


# ---------------------------------------------------------------------------
# Test: multi-page success
# ---------------------------------------------------------------------------


@mock_aws
def test_fetch_and_store_success_multi_page():
    """All records from both pages are accumulated and stored in S3."""
    _create_s3_bucket()

    page1 = _page_with_next([SAMPLE_RECORD_1], after_cursor="cursor_page2")
    page2 = _single_page_response([SAMPLE_RECORD_2])

    with (
        patch.object(fetcher_module, "_get_access_token", return_value="test_token"),
        patch.object(fetcher_module, "get_insights", side_effect=[page1, page2]),
        patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
    ):
        result = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

    assert result == EXPECTED_S3_KEY

    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket=RAW_BUCKET, Key=EXPECTED_S3_KEY)
    stored_data = json.loads(obj["Body"].read().decode("utf-8"))

    assert len(stored_data) == 2
    assert SAMPLE_RECORD_1 in stored_data
    assert SAMPLE_RECORD_2 in stored_data


# ---------------------------------------------------------------------------
# Test: rate-limit retry (succeeds on 4th attempt)
# ---------------------------------------------------------------------------


@mock_aws
def test_fetch_and_store_rate_limit_retry():
    """Retries 3 times on 429 then succeeds; get_insights called 4 times total."""
    _create_s3_bucket()

    rate_limit_error = FacebookAPIError(429, "rate limit")
    success_response = _single_page_response([SAMPLE_RECORD_1])

    side_effects = [
        rate_limit_error,
        rate_limit_error,
        rate_limit_error,
        success_response,
    ]

    with (
        patch.object(fetcher_module, "_get_access_token", return_value="test_token"),
        patch.object(fetcher_module, "get_insights", side_effect=side_effects) as mock_get,
        patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        patch("backend.services.campaign_fetcher.time.sleep") as mock_sleep,
    ):
        result = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

    # 3 failures + 1 success = 4 total calls
    assert mock_get.call_count == 4

    # sleep called 3 times with exponential backoff: 2^0=1, 2^1=2, 2^2=4
    assert mock_sleep.call_count == 3
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)
    mock_sleep.assert_any_call(4)

    assert result == EXPECTED_S3_KEY


# ---------------------------------------------------------------------------
# Test: rate-limit exhausted → DLQ routing
# ---------------------------------------------------------------------------


@mock_aws
def test_fetch_and_store_rate_limit_exhausted():
    """Raises FacebookAPIError(429) after MAX_RETRIES=5 attempts."""
    _create_s3_bucket()

    rate_limit_error = FacebookAPIError(429, "rate limit")

    with (
        patch.object(fetcher_module, "_get_access_token", return_value="test_token"),
        patch.object(fetcher_module, "get_insights", side_effect=rate_limit_error) as mock_get,
        patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        patch("backend.services.campaign_fetcher.time.sleep"),
    ):
        with pytest.raises(FacebookAPIError) as exc_info:
            fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

    assert exc_info.value.status_code == 429
    # MAX_RETRIES = 5 → exactly 5 attempts before giving up
    assert mock_get.call_count == 5


# ---------------------------------------------------------------------------
# Test: token expiry → SNS alert published, exception re-raised
# ---------------------------------------------------------------------------


@mock_aws
def test_fetch_and_store_token_expiry():
    """Raises FacebookAPIError(401) and publishes exactly one SNS alert."""
    _create_s3_bucket()

    token_error = FacebookAPIError(401, "token expired")

    mock_sns_client = MagicMock()

    def _fake_boto3_client(service, **kwargs):
        if service == "sns":
            return mock_sns_client
        # For S3, use the real moto-backed client
        return boto3.client(service, region_name="us-east-1")

    with (
        patch.object(fetcher_module, "_get_access_token", return_value="test_token"),
        patch.object(fetcher_module, "get_insights", side_effect=token_error),
        patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        patch.object(fetcher_module, "ADMIN_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:admin-alerts"),
        patch.object(fetcher_module, "boto3") as mock_boto3,
    ):
        # boto3.client("s3") must still work via moto; boto3.client("sns") returns mock
        mock_boto3.client.side_effect = _fake_boto3_client

        with pytest.raises(FacebookAPIError) as exc_info:
            fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

    assert exc_info.value.status_code == 401

    # SNS publish must have been called exactly once
    mock_sns_client.publish.assert_called_once()
    publish_kwargs = mock_sns_client.publish.call_args[1]
    assert publish_kwargs["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:admin-alerts"
    assert "expired" in publish_kwargs["Message"].lower() or "token" in publish_kwargs["Message"].lower()

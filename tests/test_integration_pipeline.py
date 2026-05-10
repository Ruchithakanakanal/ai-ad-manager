"""
tests/test_integration_pipeline.py — Integration tests for the full data pipeline.

Tests the end-to-end flow:
  S3 upload (via fetch_and_store) → data_processor.normalize_metrics
  → optimizer.generate_recommendations → DynamoDB write

AWS services (S3, DynamoDB, SNS) are mocked with moto.
SageMaker, Glue, and Bedrock calls are mocked with unittest.mock.

Requirements: 3.2, 3.7, 4.1, 5.5
"""

import json
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Environment setup — must happen BEFORE importing any backend modules
# ---------------------------------------------------------------------------

os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["DYNAMODB_RECOMMENDATIONS_TABLE"] = "Recommendations"
os.environ["RAW_BUCKET"] = "raw-bucket"
os.environ["ADMIN_SNS_TOPIC_ARN"] = ""

import backend.services.campaign_fetcher as fetcher_module  # noqa: E402
from backend.models.ad_models import OptimizationGoal  # noqa: E402
from backend.services.data_processor import normalize_metrics  # noqa: E402
from backend.services.optimizer import generate_recommendations  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNT_ID = "act_integration_test"
DATE_RANGE = {"since": "2024-03-01", "until": "2024-03-01"}
RAW_BUCKET = "raw-bucket"
RECOMMENDATIONS_TABLE = "Recommendations"

SAMPLE_RAW_RECORDS = [
    {
        "campaign_id": "camp_int_001",
        "campaign_name": "Integration Campaign A",
        "impressions": "20000",
        "clicks": "800",
        "spend": "400.00",
        "conversions": "40",
        "reach": "15000",
        "frequency": "1.33",
        "roas": "3.5",
        "date": "2024-03-01",
    },
    {
        "campaign_id": "camp_int_002",
        "campaign_name": "Integration Campaign B",
        "impressions": "5000",
        "clicks": "100",
        "spend": "200.00",
        "conversions": "5",
        "reach": "4000",
        "frequency": "1.25",
        "roas": "1.2",
        "date": "2024-03-01",
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aws_env():
    """Ensure moto uses fake credentials."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def pipeline_aws(aws_env):
    """
    Spin up moto-backed S3, DynamoDB, and SNS resources for pipeline tests.
    Yields a dict with the boto3 resource/client handles.
    """
    with mock_aws():
        # S3 raw bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=RAW_BUCKET)

        # DynamoDB Recommendations table
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=RECOMMENDATIONS_TABLE,
            KeySchema=[
                {"AttributeName": "campaign_id", "KeyType": "HASH"},
                {"AttributeName": "generated_at", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "campaign_id", "AttributeType": "S"},
                {"AttributeName": "generated_at", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # SNS topic (for alert tests)
        sns = boto3.client("sns", region_name="us-east-1")
        topic = sns.create_topic(Name="admin-alerts")

        yield {
            "s3": s3,
            "ddb": ddb,
            "sns": sns,
            "sns_topic_arn": topic["TopicArn"],
        }


# ---------------------------------------------------------------------------
# Helper: build a Facebook API single-page response
# ---------------------------------------------------------------------------


def _fb_response(records: list) -> dict:
    return {
        "data": records,
        "paging": {
            "cursors": {"before": "before_cursor", "after": "after_cursor"},
            # No "next" key → single page
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Full pipeline — fetch → normalize → recommend → DynamoDB
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """
    Integration test: S3 upload → data_processor → optimizer → DynamoDB write.
    Requirements: 3.2, 4.1, 5.5
    """

    def test_full_pipeline_writes_recommendations_to_dynamodb(self, pipeline_aws):
        """
        After running the full pipeline, one Recommendation per campaign must
        exist in DynamoDB.
        """
        ddb = pipeline_aws["ddb"]
        s3 = pipeline_aws["s3"]

        fb_response = _fb_response(SAMPLE_RAW_RECORDS)

        # ---- Step 1: fetch_and_store (S3 upload) ----
        with (
            patch.object(fetcher_module, "_get_access_token", return_value="fake-token"),
            patch.object(fetcher_module, "get_insights", return_value=fb_response),
            patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        ):
            s3_key = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

        # Verify raw data landed in S3
        obj = s3.get_object(Bucket=RAW_BUCKET, Key=s3_key)
        raw_records = json.loads(obj["Body"].read().decode("utf-8"))
        assert len(raw_records) == 2

        # ---- Step 2: normalize_metrics (data_processor) ----
        metrics = normalize_metrics(raw_records)
        assert len(metrics) == 2

        # ---- Step 3: generate_recommendations (optimizer → DynamoDB) ----
        # Mock SageMaker predictions for both campaigns
        predictions = {
            "camp_int_001": {
                "predicted_ctr": 0.045,
                "predicted_cpc": 0.48,
                "predicted_roas": 3.8,
                "confidence_score": 0.85,
            },
            "camp_int_002": {
                "predicted_ctr": 0.022,
                "predicted_cpc": 1.9,
                "predicted_roas": 1.4,
                "confidence_score": 0.72,
            },
        }

        with patch("backend.services.optimizer.generate_ad_copy_from_recommendation") as mock_copy:
            mock_copy.return_value = "Boost your campaign performance today!"
            recs = generate_recommendations(metrics, predictions, OptimizationGoal.CTR)

        assert len(recs) == 2

        # ---- Step 4: verify DynamoDB contains the recommendations ----
        table = ddb.Table(RECOMMENDATIONS_TABLE)
        for rec in recs:
            result = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("campaign_id").eq(
                    rec.campaign_id
                )
            )
            items = result["Items"]
            assert len(items) >= 1, (
                f"Expected at least 1 recommendation in DynamoDB for {rec.campaign_id}"
            )
            stored = items[0]
            assert stored["recommendation_id"] == rec.recommendation_id
            assert stored["goal"] == OptimizationGoal.CTR.value
            assert stored["applied"] is False

    def test_pipeline_recommendation_count_matches_campaign_count(self, pipeline_aws):
        """
        Exactly one recommendation is generated per campaign (Req 5.1).
        """
        fb_response = _fb_response(SAMPLE_RAW_RECORDS)

        with (
            patch.object(fetcher_module, "_get_access_token", return_value="fake-token"),
            patch.object(fetcher_module, "get_insights", return_value=fb_response),
            patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        ):
            s3_key = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

        s3 = pipeline_aws["s3"]
        raw_records = json.loads(
            s3.get_object(Bucket=RAW_BUCKET, Key=s3_key)["Body"].read().decode("utf-8")
        )
        metrics = normalize_metrics(raw_records)

        with patch("backend.services.optimizer.generate_ad_copy_from_recommendation"):
            recs = generate_recommendations(metrics, {}, OptimizationGoal.ROAS)

        assert len(recs) == len(metrics)

    def test_pipeline_with_invalid_records_excluded(self, pipeline_aws):
        """
        Records missing required fields are excluded by data_processor (Req 3.6).
        Only valid records produce recommendations.
        """
        mixed_records = [
            SAMPLE_RAW_RECORDS[0],  # valid
            {"campaign_name": "Missing ID", "impressions": "100"},  # missing campaign_id, clicks, spend
        ]

        fb_response = _fb_response(mixed_records)

        with (
            patch.object(fetcher_module, "_get_access_token", return_value="fake-token"),
            patch.object(fetcher_module, "get_insights", return_value=fb_response),
            patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        ):
            s3_key = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

        s3 = pipeline_aws["s3"]
        raw_records = json.loads(
            s3.get_object(Bucket=RAW_BUCKET, Key=s3_key)["Body"].read().decode("utf-8")
        )

        # data_processor should exclude the invalid record
        metrics = normalize_metrics(raw_records)
        assert len(metrics) == 1
        assert metrics[0].campaign_id == "camp_int_001"

        with patch("backend.services.optimizer.generate_ad_copy_from_recommendation"):
            recs = generate_recommendations(metrics, {}, OptimizationGoal.CPC)

        assert len(recs) == 1

    def test_pipeline_s3_object_has_sse_encryption(self, pipeline_aws):
        """
        Raw data written to S3 must use SSE-S3 server-side encryption (Req 3.1).
        """
        fb_response = _fb_response([SAMPLE_RAW_RECORDS[0]])

        with (
            patch.object(fetcher_module, "_get_access_token", return_value="fake-token"),
            patch.object(fetcher_module, "get_insights", return_value=fb_response),
            patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        ):
            s3_key = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

        s3 = pipeline_aws["s3"]
        head = s3.head_object(Bucket=RAW_BUCKET, Key=s3_key)
        assert head.get("ServerSideEncryption") == "AES256", (
            "S3 object must be encrypted with SSE-S3 (AES256)"
        )

    def test_pipeline_rule_based_fallback_when_no_predictions(self, pipeline_aws):
        """
        When SageMaker predictions are absent, rule-based fallback is used and
        recommendations are still written to DynamoDB (Req 4.4, 5.5).
        """
        ddb = pipeline_aws["ddb"]
        metrics = normalize_metrics(SAMPLE_RAW_RECORDS)

        with patch("backend.services.optimizer.generate_ad_copy_from_recommendation"):
            # Empty predictions dict → rule-based fallback for all campaigns
            recs = generate_recommendations(metrics, {}, OptimizationGoal.CONVERSION)

        assert len(recs) == 2

        table = ddb.Table(RECOMMENDATIONS_TABLE)
        for rec in recs:
            result = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("campaign_id").eq(
                    rec.campaign_id
                )
            )
            assert len(result["Items"]) >= 1, (
                f"Rule-based recommendation for {rec.campaign_id} not found in DynamoDB"
            )
            # Rule-based fallback always sets confidence_score = 0.5
            assert rec.confidence_score == 0.5

    def test_pipeline_multi_page_fetch_accumulates_all_records(self, pipeline_aws):
        """
        When Facebook API returns paginated results, all pages are accumulated
        before writing to S3 (Req 2.4, 3.2).
        """
        page1 = {
            "data": [SAMPLE_RAW_RECORDS[0]],
            "paging": {
                "cursors": {"before": "b", "after": "cursor_page2"},
                "next": "https://graph.facebook.com/v18.0/act_123/insights?after=cursor_page2",
            },
        }
        page2 = {
            "data": [SAMPLE_RAW_RECORDS[1]],
            "paging": {
                "cursors": {"before": "b", "after": "cursor_end"},
                # No "next" → last page
            },
        }

        with (
            patch.object(fetcher_module, "_get_access_token", return_value="fake-token"),
            patch.object(fetcher_module, "get_insights", side_effect=[page1, page2]),
            patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
        ):
            s3_key = fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

        s3 = pipeline_aws["s3"]
        raw_records = json.loads(
            s3.get_object(Bucket=RAW_BUCKET, Key=s3_key)["Body"].read().decode("utf-8")
        )
        assert len(raw_records) == 2, "Both pages must be accumulated in S3"

    def test_pipeline_confidence_scores_in_valid_range(self, pipeline_aws):
        """
        All generated recommendations must have confidence_score in [0.0, 1.0] (Req 5.3).
        """
        metrics = normalize_metrics(SAMPLE_RAW_RECORDS)
        predictions = {
            "camp_int_001": {"predicted_ctr": 0.05, "confidence_score": 0.9},
            "camp_int_002": {"predicted_ctr": 0.02, "confidence_score": 0.4},
        }

        with patch("backend.services.optimizer.generate_ad_copy_from_recommendation"):
            recs = generate_recommendations(metrics, predictions, OptimizationGoal.CTR)

        for rec in recs:
            assert 0.0 <= rec.confidence_score <= 1.0, (
                f"confidence_score {rec.confidence_score} out of [0, 1] for {rec.campaign_id}"
            )

    def test_pipeline_suggested_value_within_guardrail(self, pipeline_aws):
        """
        suggested_value must not deviate more than 50% from current_value (Req 5.2).
        """
        metrics = normalize_metrics(SAMPLE_RAW_RECORDS)
        # Provide extreme predictions to test guardrail clamping
        predictions = {
            "camp_int_001": {"predicted_ctr": 999.0, "confidence_score": 0.9},
            "camp_int_002": {"predicted_ctr": 0.0001, "confidence_score": 0.9},
        }

        with patch("backend.services.optimizer.generate_ad_copy_from_recommendation"):
            recs = generate_recommendations(metrics, predictions, OptimizationGoal.CTR)

        for rec in recs:
            lower = rec.current_value * 0.5
            upper = rec.current_value * 1.5
            assert lower <= rec.suggested_value <= upper, (
                f"suggested_value {rec.suggested_value} outside guardrail "
                f"[{lower}, {upper}] for {rec.campaign_id}"
            )

    # Aliases matching the task-specified test names for traceability
    test_full_pipeline_s3_to_dynamodb = test_full_pipeline_writes_recommendations_to_dynamodb
    test_pipeline_with_missing_fields_excluded = test_pipeline_with_invalid_records_excluded


# ---------------------------------------------------------------------------
# Test 2: SNS alert published on Facebook token expiry (Req 3.7)
# ---------------------------------------------------------------------------


class TestPipelineSNSAlertOnTokenExpiry:
    """
    Integration test: Facebook 401 → SNS alert published to admin topic.
    Requirements: 3.7
    """

    def test_pipeline_sns_alert_on_token_expiry(self, pipeline_aws):
        """
        When the Facebook API returns HTTP 401 (token expired), fetch_and_store
        must publish exactly one SNS message to the admin topic and re-raise
        the FacebookAPIError.

        Validates: Requirements 3.7
        """
        from backend.integrations.fb_client import FacebookAPIError

        sns_topic_arn = pipeline_aws["sns_topic_arn"]

        token_error = FacebookAPIError(401, "Invalid OAuth access token")

        # Patch ADMIN_SNS_TOPIC_ARN to point at our moto-backed SNS topic
        with (
            patch.object(fetcher_module, "_get_access_token", return_value="expired-token"),
            patch.object(fetcher_module, "get_insights", side_effect=token_error),
            patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
            patch.object(fetcher_module, "ADMIN_SNS_TOPIC_ARN", sns_topic_arn),
        ):
            with pytest.raises(FacebookAPIError) as exc_info:
                fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

        # Exception must be the 401 token expiry error
        assert exc_info.value.status_code == 401

        # Verify SNS message was published to the admin topic
        sns = pipeline_aws["sns"]
        # Use SQS subscription to capture the published message
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="test-alert-queue")
        queue_url = queue["QueueUrl"]
        queue_attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["QueueArn"]
        )
        queue_arn = queue_attrs["Attributes"]["QueueArn"]

        # Subscribe SQS to the SNS topic (retroactively check via list_subscriptions)
        # Since the message was already published, we verify via SNS subscription listing
        # and confirm the publish call happened by checking the topic's message count
        # via a fresh subscription + re-publish approach.
        #
        # Moto tracks published messages; we verify by subscribing and re-publishing.
        # The simplest approach: subscribe SQS, publish a test message, confirm delivery.
        # For the token-expiry test, we verify the SNS publish was called by patching
        # the SNS client directly.

        # Re-run with a patched SNS client to capture the publish call
        mock_sns_client = MagicMock()

        def _fake_boto3_client(service, **kwargs):
            if service == "sns":
                return mock_sns_client
            # For secretsmanager, return a mock too
            if service == "secretsmanager":
                m = MagicMock()
                m.get_secret_value.return_value = {"SecretString": "fake-token"}
                return m
            return boto3.client(service, region_name="us-east-1")

        with (
            patch.object(fetcher_module, "get_insights", side_effect=token_error),
            patch.object(fetcher_module, "RAW_BUCKET", RAW_BUCKET),
            patch.object(fetcher_module, "ADMIN_SNS_TOPIC_ARN", sns_topic_arn),
            patch.object(fetcher_module, "boto3") as mock_boto3,
        ):
            mock_boto3.client.side_effect = _fake_boto3_client

            with pytest.raises(FacebookAPIError):
                fetcher_module.fetch_and_store(ACCOUNT_ID, DATE_RANGE)

        # SNS publish must have been called exactly once
        mock_sns_client.publish.assert_called_once()
        publish_kwargs = mock_sns_client.publish.call_args[1]
        assert publish_kwargs["TopicArn"] == sns_topic_arn
        # Message must mention token expiry
        message_text = publish_kwargs["Message"].lower()
        assert "token" in message_text or "expired" in message_text or "401" in message_text

"""
Unit tests for backend/services/optimizer.py

Covers:
- Guardrail enforcement (Req 5.2)
- Low-confidence flagging (Req 5.4)
- DynamoDB retry logic (Req 5.6)
- Rule-based fallback (Req 5.6)
- check_and_alert: below threshold, above threshold, no-match, low-confidence skip (Req 7.3, 7.4, 7.5)
"""

import uuid
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

from backend.models.ad_models import AlertConfig, CampaignMetrics, OptimizationGoal, Recommendation
from backend.services.optimizer import _write_to_dynamodb, check_and_alert, generate_recommendations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_metrics(campaign_id="camp_1", ctr=0.05, cpc=1.0, roas=2.0, conversions=10) -> CampaignMetrics:
    return CampaignMetrics(
        campaign_id=campaign_id,
        campaign_name="Test Campaign",
        date="2024-01-15",
        impressions=1000,
        clicks=50,
        spend=50.0,
        conversions=conversions,
        ctr=ctr,
        cpc=cpc,
        roas=roas,
        reach=5000,
        frequency=1.5,
    )


def make_recommendation(
    campaign_id="camp_1",
    current_value=0.05,
    confidence_score=0.8,
) -> Recommendation:
    return Recommendation(
        recommendation_id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        generated_at="2024-01-15T12:00:00",
        goal=OptimizationGoal.CTR,
        action="increase_bid",
        current_value=current_value,
        suggested_value=current_value * 1.1,
        confidence_score=confidence_score,
        reasoning="Test reasoning",
    )


def make_alert_config(
    campaign_id="camp_1",
    metric="ctr",
    threshold=0.05,
    direction="below",
    sns_topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
) -> AlertConfig:
    return AlertConfig(
        user_id="user_1",
        campaign_id=campaign_id,
        metric=metric,
        threshold=threshold,
        direction=direction,
        sns_topic_arn=sns_topic_arn,
    )


# ---------------------------------------------------------------------------
# 1. Guardrail enforcement
# ---------------------------------------------------------------------------

def test_guardrail_enforcement():
    """
    When a prediction suggests a value > 1.5x current_value, the output
    suggested_value must be clamped to current_value * 1.5.
    Validates: Requirements 5.2
    """
    metrics = make_metrics(ctr=0.04)
    # Prediction suggests 3x the current CTR — well beyond the 50% guardrail
    predictions = {
        "camp_1": {
            "predicted_ctr": 0.12,  # 3x current 0.04
            "predicted_cpc": 1.0,
            "predicted_roas": 2.0,
            "confidence_score": 0.9,
        }
    }

    with patch("backend.services.optimizer._write_to_dynamodb"):
        recs = generate_recommendations([metrics], predictions, OptimizationGoal.CTR)

    assert len(recs) == 1
    rec = recs[0]
    expected_max = 0.04 * 1.5
    assert rec.suggested_value <= expected_max, (
        f"suggested_value {rec.suggested_value} exceeds guardrail ceiling {expected_max}"
    )
    assert abs(rec.suggested_value - expected_max) < 1e-9, (
        f"Expected suggested_value to be clamped to {expected_max}, got {rec.suggested_value}"
    )


# ---------------------------------------------------------------------------
# 2. Low-confidence flagging
# ---------------------------------------------------------------------------

def test_low_confidence_flagging():
    """
    When confidence_score < 0.6, reasoning must contain '[LOW CONFIDENCE'.
    Validates: Requirements 5.4
    """
    metrics = make_metrics()
    predictions = {
        "camp_1": {
            "predicted_ctr": 0.06,
            "predicted_cpc": 1.0,
            "predicted_roas": 2.0,
            "confidence_score": 0.3,
        }
    }

    with patch("backend.services.optimizer._write_to_dynamodb"):
        recs = generate_recommendations([metrics], predictions, OptimizationGoal.CTR)

    assert len(recs) == 1
    assert "[LOW CONFIDENCE" in recs[0].reasoning, (
        f"Expected '[LOW CONFIDENCE' in reasoning, got: {recs[0].reasoning}"
    )


def test_high_confidence_no_flag():
    """
    When confidence_score >= 0.6, reasoning must NOT contain '[LOW CONFIDENCE'.
    Validates: Requirements 5.4
    """
    metrics = make_metrics()
    predictions = {
        "camp_1": {
            "predicted_ctr": 0.06,
            "predicted_cpc": 1.0,
            "predicted_roas": 2.0,
            "confidence_score": 0.9,
        }
    }

    with patch("backend.services.optimizer._write_to_dynamodb"):
        recs = generate_recommendations([metrics], predictions, OptimizationGoal.CTR)

    assert len(recs) == 1
    assert "[LOW CONFIDENCE" not in recs[0].reasoning, (
        f"Did not expect '[LOW CONFIDENCE' in reasoning, got: {recs[0].reasoning}"
    )


# ---------------------------------------------------------------------------
# 3. DynamoDB retry on failure
# ---------------------------------------------------------------------------

def test_dynamodb_retry_on_failure():
    """
    _write_to_dynamodb retries up to 3 times total when put_item raises
    ClientError. Verifies put_item is called exactly 3 times when it fails
    twice then succeeds.
    Validates: Requirements 5.6
    """
    error_response = {
        "Error": {
            "Code": "ProvisionedThroughputExceededException",
            "Message": "Throughput exceeded",
        }
    }
    client_error = ClientError(error_response, "PutItem")

    mock_table = MagicMock()
    # Fail twice, succeed on third attempt
    mock_table.put_item.side_effect = [client_error, client_error, None]

    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    rec = make_recommendation()

    with patch("backend.services.optimizer.boto3.resource", return_value=mock_dynamodb):
        with patch("backend.services.optimizer.time.sleep"):  # skip actual sleep
            _write_to_dynamodb(rec)

    assert mock_table.put_item.call_count == 3, (
        f"Expected put_item to be called 3 times, got {mock_table.put_item.call_count}"
    )


# ---------------------------------------------------------------------------
# 4. Rule-based fallback
# ---------------------------------------------------------------------------

def test_rule_based_fallback():
    """
    When predictions dict is empty, generate_recommendations falls back to
    rule-based logic and still returns one Recommendation per campaign.
    Validates: Requirements 5.6
    """
    metrics_list = [make_metrics("camp_1"), make_metrics("camp_2")]

    with patch("backend.services.optimizer._write_to_dynamodb") as mock_write:
        recs = generate_recommendations(metrics_list, {}, OptimizationGoal.CTR)

    assert len(recs) == 2, f"Expected 2 recommendations, got {len(recs)}"
    assert mock_write.call_count == 2
    for rec in recs:
        assert rec.confidence_score == 0.5  # rule-based always returns 0.5


# ---------------------------------------------------------------------------
# 5. check_and_alert — below threshold
# ---------------------------------------------------------------------------

def test_check_and_alert_below_threshold():
    """
    When direction='below' and current_value < threshold, SNS publish is called.
    Validates: Requirements 7.3, 7.4
    """
    rec = make_recommendation(current_value=0.02, confidence_score=0.8)
    config = make_alert_config(direction="below", threshold=0.05)

    mock_sns = MagicMock()
    with patch("backend.services.optimizer.boto3.client", return_value=mock_sns):
        check_and_alert(rec, [config])

    mock_sns.publish.assert_called_once()
    call_kwargs = mock_sns.publish.call_args.kwargs
    assert call_kwargs["TopicArn"] == config.sns_topic_arn


# ---------------------------------------------------------------------------
# 6. check_and_alert — above threshold
# ---------------------------------------------------------------------------

def test_check_and_alert_above_threshold():
    """
    When direction='above' and current_value > threshold, SNS publish is called.
    Validates: Requirements 7.3, 7.5
    """
    rec = make_recommendation(current_value=0.05, confidence_score=0.8)
    config = make_alert_config(direction="above", threshold=0.01)

    mock_sns = MagicMock()
    with patch("backend.services.optimizer.boto3.client", return_value=mock_sns):
        check_and_alert(rec, [config])

    mock_sns.publish.assert_called_once()


# ---------------------------------------------------------------------------
# 7. check_and_alert — no matching campaign
# ---------------------------------------------------------------------------

def test_check_and_alert_no_match():
    """
    When AlertConfig is for a different campaign_id, SNS publish is NOT called.
    Validates: Requirements 7.3
    """
    rec = make_recommendation(campaign_id="camp_1", current_value=0.02, confidence_score=0.8)
    config = make_alert_config(campaign_id="camp_OTHER", direction="below", threshold=0.05)

    mock_sns = MagicMock()
    with patch("backend.services.optimizer.boto3.client", return_value=mock_sns):
        check_and_alert(rec, [config])

    mock_sns.publish.assert_not_called()


# ---------------------------------------------------------------------------
# 8. check_and_alert — low confidence skipped
# ---------------------------------------------------------------------------

def test_check_and_alert_low_confidence_skipped():
    """
    When confidence_score < 0.6, check_and_alert skips all configs and does
    not publish to SNS.
    Validates: Requirements 7.3
    """
    rec = make_recommendation(current_value=0.02, confidence_score=0.4)
    config = make_alert_config(direction="below", threshold=0.05)

    mock_sns = MagicMock()
    with patch("backend.services.optimizer.boto3.client", return_value=mock_sns):
        check_and_alert(rec, [config])

    mock_sns.publish.assert_not_called()

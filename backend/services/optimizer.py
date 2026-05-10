"""
optimizer.py — AI-driven recommendation generation service.

Generates one Recommendation per CampaignMetrics entry using SageMaker predictions
(or rule-based fallback), enforces a 50% guardrail on suggested values, flags
low-confidence results, and persists each recommendation to DynamoDB with retries.
"""

import logging
import os
import time
import uuid
from datetime import datetime, UTC

datetime.now(UTC)
import boto3
from botocore.exceptions import ClientError

from backend.models.ad_models import AlertConfig, CampaignMetrics, OptimizationGoal, Recommendation
from backend.services.ai_engine import generate_ad_copy_from_recommendation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DYNAMODB_TABLE = os.environ.get("DYNAMODB_RECOMMENDATIONS_TABLE", "Recommendations")
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # seconds; actual sleep = _BACKOFF_BASE * 2^attempt

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_guardrail(current_value: float, suggested_value: float) -> float:
    """Clamp suggested_value so it never deviates more than 50% from current_value."""
    lower = current_value * 0.5
    upper = current_value * 1.5
    return max(lower, min(suggested_value, upper))


def _rule_based_recommendation(
    metrics: CampaignMetrics, goal: OptimizationGoal
) -> tuple[str, float, float, float]:
    """
    Produce (action, current_value, suggested_value, confidence_score) using
    deterministic rule-based logic when SageMaker predictions are unavailable.
    """
    if goal == OptimizationGoal.CTR:
        current = metrics.ctr
        suggested = _apply_guardrail(current, current * 1.1)
        return "increase_bid", current, suggested, 0.5

    if goal == OptimizationGoal.CPC:
        current = metrics.cpc
        suggested = _apply_guardrail(current, current * 0.9)
        return "decrease_bid", current, suggested, 0.5

    if goal == OptimizationGoal.CONVERSION:
        current = float(metrics.conversions)
        suggested = _apply_guardrail(current, current * 1.2)
        return "narrow_audience", current, suggested, 0.5

    # ROAS
    current = metrics.roas
    suggested = _apply_guardrail(current, current * 1.15)
    return "reallocate_budget", current, suggested, 0.5


def _ml_based_recommendation(
    metrics: CampaignMetrics,
    prediction: dict,
    goal: OptimizationGoal,
) -> tuple[str, float, float, float]:
    """
    Derive (action, current_value, suggested_value, confidence_score) from
    SageMaker prediction output for a single campaign.
    """
    confidence = float(prediction.get("confidence_score", 0.5))
    confidence = max(0.0, min(confidence, 1.0))

    if goal == OptimizationGoal.CTR:
        current = metrics.ctr
        suggested = _apply_guardrail(current, float(prediction.get("predicted_ctr", current)))
        return "increase_bid", current, suggested, confidence

    if goal == OptimizationGoal.CPC:
        current = metrics.cpc
        suggested = _apply_guardrail(current, float(prediction.get("predicted_cpc", current)))
        return "decrease_bid", current, suggested, confidence

    if goal == OptimizationGoal.CONVERSION:
        current = float(metrics.conversions)
        # Use predicted ROAS as a proxy signal; fall back to rule-based multiplier
        suggested = _apply_guardrail(current, current * 1.2)
        return "narrow_audience", current, suggested, confidence

    # ROAS
    current = metrics.roas
    suggested = _apply_guardrail(current, float(prediction.get("predicted_roas", current)))
    return "reallocate_budget", current, suggested, confidence


def _write_to_dynamodb(recommendation: Recommendation) -> None:
    """
    Write a Recommendation to DynamoDB with up to _MAX_RETRIES retries and
    exponential backoff. Logs an error to CloudWatch after all retries are
    exhausted.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_TABLE)

    item = {
        "campaign_id": recommendation.campaign_id,
        "generated_at": recommendation.generated_at,
        "recommendation_id": recommendation.recommendation_id,
        "goal": recommendation.goal.value,
        "action": recommendation.action,
        "current_value": str(recommendation.current_value),
        "suggested_value": str(recommendation.suggested_value),
        "confidence_score": str(recommendation.confidence_score),
        "reasoning": recommendation.reasoning,
        "applied": recommendation.applied,
    }

    for attempt in range(_MAX_RETRIES):
        try:
            table.put_item(Item=item)
            return
        except ClientError as exc:
            if attempt < _MAX_RETRIES - 1:
                sleep_time = _BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "DynamoDB write failed (attempt %d/%d) for recommendation %s: %s — retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    recommendation.recommendation_id,
                    exc,
                    sleep_time,
                )
                time.sleep(sleep_time)
            else:
                logger.error(
                    "DynamoDB write permanently failed for recommendation %s after %d attempts: %s",
                    recommendation.recommendation_id,
                    _MAX_RETRIES,
                    exc,
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_recommendations(
    metrics: list[CampaignMetrics],
    predictions: dict,
    goal: OptimizationGoal,
) -> list[Recommendation]:
    """
    Generate exactly one Recommendation per campaign in *metrics*.

    Parameters
    ----------
    metrics:
        Normalised campaign performance data (one entry per campaign).
    predictions:
        SageMaker inference output keyed by campaign_id.  If a campaign_id is
        absent (e.g. SageMaker timed out), rule-based fallback logic is used
        and the fallback event is logged to CloudWatch.
    goal:
        The optimisation objective shared by all campaigns in this batch.

    Returns
    -------
    list[Recommendation]
        One Recommendation per entry in *metrics*, written to DynamoDB.
    """
    recommendations: list[Recommendation] = []

    for campaign_metrics in metrics:
        cid = campaign_metrics.campaign_id
        prediction = predictions.get(cid)

        if prediction is None:
            # SageMaker result missing — use rule-based fallback
            logger.warning(
                "No SageMaker prediction for campaign %s — falling back to rule-based logic. "
                "This may indicate a SageMaker endpoint timeout.",
                cid,
            )
            action, current_value, suggested_value, confidence_score = _rule_based_recommendation(
                campaign_metrics, goal
            )
        else:
            action, current_value, suggested_value, confidence_score = _ml_based_recommendation(
                campaign_metrics, prediction, goal
            )

        # Guardrail: ensure suggested_value stays within ±50% of current_value
        suggested_value = _apply_guardrail(current_value, suggested_value)

        # Confidence must be in [0.0, 1.0]
        confidence_score = max(0.0, min(confidence_score, 1.0))

        # Build reasoning string; flag low-confidence results
        if confidence_score < 0.6:
            reasoning = (
                f"[LOW CONFIDENCE: {confidence_score:.2f}] "
                f"Recommended action '{action}' for goal {goal.value}. "
                f"Current value: {current_value:.4f}, suggested value: {suggested_value:.4f}."
            )
        else:
            reasoning = (
                f"Recommended action '{action}' for goal {goal.value} "
                f"(confidence: {confidence_score:.2f}). "
                f"Current value: {current_value:.4f}, suggested value: {suggested_value:.4f}."
            )

        rec = Recommendation(
            recommendation_id=str(uuid.uuid4()),
            campaign_id=cid,
            generated_at=datetime.utcnow().isoformat(),
            goal=goal,
            action=action,
            current_value=current_value,
            suggested_value=suggested_value,
            confidence_score=confidence_score,
            reasoning=reasoning,
        )

        _write_to_dynamodb(rec)

        # Optionally generate ad copy via Bedrock (failures are non-fatal)
        try:
            ad_copy = generate_ad_copy_from_recommendation(rec)
            logger.info(
                "Ad copy for campaign %s: %s",
                cid,
                ad_copy,
            )
        except Exception as exc:
            logger.warning(
                "Ad copy generation skipped for campaign %s: %s",
                cid,
                exc,
            )

        recommendations.append(rec)

    return recommendations


def check_and_alert(rec: Recommendation, configs: list[AlertConfig]) -> None:
    """
    Evaluate AlertConfig thresholds for *rec* and publish SNS notifications
    when a threshold is breached.

    Only evaluates configs when rec.confidence_score >= 0.6.

    For each AlertConfig whose campaign_id matches rec.campaign_id:
    - direction="below": publish if rec.current_value < threshold
    - direction="above": publish if rec.current_value > threshold
    """
    if rec.confidence_score < 0.6:
        return

    sns_client = boto3.client("sns")

    for config in configs:
        if config.campaign_id != rec.campaign_id:
            continue

        current = rec.current_value
        breached = (
            (config.direction == "below" and current < config.threshold)
            or (config.direction == "above" and current > config.threshold)
        )

        if not breached:
            continue

        subject = f"Campaign Alert: {config.metric} threshold breached for {rec.campaign_id}"
        message = (
            f"Campaign ID: {rec.campaign_id}\n"
            f"Metric: {config.metric}\n"
            f"Current value: {current}\n"
            f"Threshold: {config.threshold}\n"
            f"Direction: {config.direction}\n"
            f"Confidence score: {rec.confidence_score:.2f}"
        )

        try:
            sns_client.publish(
                TopicArn=config.sns_topic_arn,
                Message=message,
                Subject=subject,
            )
            logger.info(
                "Alert published for campaign %s: %s %s threshold %.4f (current %.4f)",
                rec.campaign_id,
                config.metric,
                config.direction,
                config.threshold,
                current,
            )
        except ClientError as exc:
            logger.error(
                "Failed to publish SNS alert for campaign %s metric %s: %s",
                rec.campaign_id,
                config.metric,
                exc,
            )

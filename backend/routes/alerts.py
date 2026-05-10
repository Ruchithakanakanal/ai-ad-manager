"""
backend/routes/alerts.py — Alert configuration endpoints.

GET  /alerts — return all AlertConfigs for the authenticated user
POST /alerts — create or update an AlertConfig in DynamoDB (Analyst/Admin only)
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth_utils import get_current_user, require_analyst_or_admin
from backend.models.ad_models import AlertConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

ALERT_CONFIGS_TABLE = os.environ.get("DYNAMODB_ALERT_CONFIGS_TABLE", "AlertConfigs")


def _get_dynamodb_resource():
    """Return a boto3 DynamoDB resource."""
    return boto3.resource("dynamodb")


@router.get("", status_code=status.HTTP_200_OK)
def list_alerts(
    payload: dict = Depends(get_current_user),
) -> list[dict]:
    """
    Return all AlertConfig records belonging to the authenticated user.

    Requires a valid JWT (any role).
    """
    user_id = payload.get("sub") or payload.get("email") or ""

    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table(ALERT_CONFIGS_TABLE)

    try:
        from boto3.dynamodb.conditions import Key

        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
        )
        items: list[dict] = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression=Key("user_id").eq(user_id),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

    except ClientError as exc:
        logger.error("DynamoDB query failed for alerts of user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert configurations",
        )

    return items


@router.post("", status_code=status.HTTP_200_OK)
def create_or_update_alert(
    body: AlertConfig,
    payload: dict = Depends(require_analyst_or_admin),
) -> dict:
    """
    Create or update an AlertConfig in DynamoDB.

    Requires Analyst or Admin role (HTTP 403 for Viewer).

    The DynamoDB key is:
      PK: user_id
      SK: campaign_id#metric
    """
    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table(ALERT_CONFIGS_TABLE)

    # Derive the sort key from the AlertConfig
    sk = f"{body.campaign_id}#{body.metric}"

    item = {
        "user_id": body.user_id,
        "campaign_id_metric": sk,
        "campaign_id": body.campaign_id,
        "metric": body.metric,
        "threshold": str(body.threshold),  # DynamoDB stores as string for Decimal safety
        "direction": body.direction,
        "sns_topic_arn": body.sns_topic_arn,
    }

    try:
        table.put_item(Item=item)
    except ClientError as exc:
        logger.error(
            "DynamoDB put_item failed for alert config user=%s campaign=%s metric=%s: %s",
            body.user_id,
            body.campaign_id,
            body.metric,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save alert configuration",
        )

    return {
        "status": "saved",
        "user_id": body.user_id,
        "campaign_id": body.campaign_id,
        "metric": body.metric,
        "threshold": body.threshold,
        "direction": body.direction,
    }

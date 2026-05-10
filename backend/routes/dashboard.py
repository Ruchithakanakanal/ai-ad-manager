"""
backend/routes/dashboard.py — Dashboard summary endpoint.

GET /dashboard/summary — Aggregate KPIs across all campaigns from DynamoDB.
"""

import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth_utils import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

METRICS_TABLE = os.environ.get("DYNAMODB_METRICS_TABLE", "CampaignMetrics")


def _get_dynamodb_resource():
    """Return a boto3 DynamoDB resource."""
    return boto3.resource("dynamodb")


def _to_float(value) -> float:
    """Safely convert Decimal or other numeric types to float."""
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@router.get("/summary", status_code=status.HTTP_200_OK)
def get_dashboard_summary(
    _payload: dict = Depends(get_current_user),
) -> dict:
    """
    Return aggregated KPIs across all campaigns.

    Scans the CampaignMetrics table, takes the latest record per campaign,
    and aggregates: total_spend, total_impressions, total_clicks,
    total_conversions, avg_ctr, avg_cpc, avg_roas, campaign_count.

    Requires a valid JWT (any role).
    Target response time: < 2 seconds under normal load.
    """
    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table(METRICS_TABLE)

    try:
        response = table.scan()
        items: list[dict] = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))

    except ClientError as exc:
        logger.error("DynamoDB scan failed for dashboard summary: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve campaign data",
        )

    # Keep only the latest record per campaign_id
    latest: dict[str, dict] = {}
    for item in items:
        cid = item.get("campaign_id", "")
        existing = latest.get(cid)
        if existing is None or item.get("date", "") > existing.get("date", ""):
            latest[cid] = item

    campaigns = list(latest.values())
    count = len(campaigns)

    if count == 0:
        return {
            "campaign_count": 0,
            "total_spend": 0.0,
            "total_impressions": 0,
            "total_clicks": 0,
            "total_conversions": 0,
            "avg_ctr": 0.0,
            "avg_cpc": 0.0,
            "avg_roas": 0.0,
        }

    total_spend = sum(_to_float(c.get("spend", 0)) for c in campaigns)
    total_impressions = sum(int(c.get("impressions", 0)) for c in campaigns)
    total_clicks = sum(int(c.get("clicks", 0)) for c in campaigns)
    total_conversions = sum(int(c.get("conversions", 0)) for c in campaigns)

    avg_ctr = sum(_to_float(c.get("ctr", 0)) for c in campaigns) / count
    avg_cpc = sum(_to_float(c.get("cpc", 0)) for c in campaigns) / count
    avg_roas = sum(_to_float(c.get("roas", 0)) for c in campaigns) / count

    return {
        "campaign_count": count,
        "total_spend": round(total_spend, 4),
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_conversions": total_conversions,
        "avg_ctr": round(avg_ctr, 6),
        "avg_cpc": round(avg_cpc, 4),
        "avg_roas": round(avg_roas, 4),
    }

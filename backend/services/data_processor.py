import logging
from backend.models.ad_models import CampaignMetrics

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"campaign_id", "impressions", "clicks", "spend"}


def normalize_metrics(raw_records: list[dict]) -> list[CampaignMetrics]:
    """
    Validate and normalize raw Facebook Ads records into CampaignMetrics objects.

    - Computes ctr = clicks / impressions (0.0 if impressions == 0)
    - Computes cpc = spend / clicks (0.0 if clicks == 0)
    - Logs a warning and excludes records missing required fields
      (campaign_id, impressions, clicks, spend)
    """
    results: list[CampaignMetrics] = []

    for record in raw_records:
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            logger.warning(
                "Excluding record due to missing required fields %s: %s",
                sorted(missing),
                record,
            )
            continue

        try:
            impressions = int(record["impressions"])
            clicks = int(record["clicks"])
            spend = float(record["spend"])
        except (ValueError, TypeError) as exc:
            logger.warning("Excluding record due to invalid numeric field: %s — %s", record, exc)
            continue

        ctr = clicks / impressions if impressions != 0 else 0.0
        cpc = spend / clicks if clicks != 0 else 0.0

        metrics = CampaignMetrics(
            campaign_id=str(record["campaign_id"]),
            campaign_name=str(record.get("campaign_name", "")),
            date=str(record.get("date", "")),
            impressions=impressions,
            clicks=clicks,
            spend=spend,
            conversions=int(record.get("conversions", 0)),
            ctr=ctr,
            cpc=cpc,
            roas=float(record.get("roas", 0.0)),
            reach=int(record.get("reach", 0)),
            frequency=float(record.get("frequency", 0.0)),
        )
        results.append(metrics)

    return results


def build_feature_vector(metrics: CampaignMetrics) -> list[float]:
    """
    Extract numeric fields from a CampaignMetrics object into a float feature vector.

    Order: [impressions, clicks, spend, conversions, ctr, cpc, roas, reach, frequency]
    """
    return [
        float(metrics.impressions),
        float(metrics.clicks),
        float(metrics.spend),
        float(metrics.conversions),
        float(metrics.ctr),
        float(metrics.cpc),
        float(metrics.roas),
        float(metrics.reach),
        float(metrics.frequency),
    ]

"""
Facebook Ads API client.

Access tokens must be retrieved from AWS Secrets Manager by the caller
and passed in — this module never reads tokens from env vars or code.
"""

import json
import requests

FB_API_BASE = "https://graph.facebook.com/v18.0"


class FacebookAPIError(Exception):
    """Raised when the Facebook Ads API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"FacebookAPIError {status_code}: {message}")


def get_insights(
    account_id: str,
    date_range: dict,
    access_token: str,
    fields: str,
    after: str | None = None,
) -> dict:
    """
    Call the Facebook Ads Insights API for a single page of results.

    Args:
        account_id:   Ad account ID, e.g. "act_123456789".
        date_range:   Dict with "since" and "until" keys (YYYY-MM-DD strings).
        access_token: Valid Facebook user/system access token (caller retrieves
                      this from AWS Secrets Manager — never stored here).
        fields:       Comma-separated field names, e.g.
                      "campaign_id,impressions,clicks,spend,date_start,date_stop".
        after:        Pagination cursor returned by a previous call's
                      ``paging.cursors.after`` value.  Pass ``None`` for the
                      first page.

    Returns:
        The raw JSON response dict, which contains:
          - ``data``:   list of insight records for this page.
          - ``paging``: dict with ``cursors`` (``before``/``after``) and
                        optionally a ``next`` URL when more pages exist.

    Raises:
        FacebookAPIError: If the API returns a non-2xx HTTP status code.
    """
    url = f"{FB_API_BASE}/{account_id}/insights"

    params: dict = {
        "fields": fields,
        "time_range": json.dumps(date_range),
        "access_token": access_token,
    }

    if after is not None:
        params["after"] = after

    response = requests.get(url, params=params, timeout=30)

    if not response.ok:
        # Try to extract a human-readable error message from the FB error body.
        try:
            error_body = response.json()
            message = (
                error_body.get("error", {}).get("message", response.text)
            )
        except Exception:
            message = response.text

        raise FacebookAPIError(response.status_code, message)

    return response.json()


def apply_recommendation(
    campaign_id: str,
    update_payload: dict,
    access_token: str,
) -> bool:
    """
    Apply a bid/budget/audience update to a Facebook campaign.

    Args:
        campaign_id:    Facebook campaign ID.
        update_payload: Dict of fields to update (e.g. {"daily_budget": 5000}).
        access_token:   Valid Facebook access token (from Secrets Manager).

    Returns:
        True on success.

    Raises:
        FacebookAPIError: If the API returns a non-2xx HTTP status code.
    """
    url = f"{FB_API_BASE}/{campaign_id}"

    payload = {**update_payload, "access_token": access_token}

    response = requests.post(url, data=payload, timeout=30)

    if not response.ok:
        try:
            error_body = response.json()
            message = error_body.get("error", {}).get("message", response.text)
        except Exception:
            message = response.text

        raise FacebookAPIError(response.status_code, message)

    return True

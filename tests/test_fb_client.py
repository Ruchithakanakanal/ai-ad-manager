"""
Unit tests for backend/integrations/fb_client.py

Covers:
- get_insights: success, 429 rate limit, 401 expired token, network error, pagination cursor
- apply_recommendation: success, failure (400)

Requirements: 2.5, 2.6, 2.7
"""

import json
import pytest
import requests
from unittest.mock import patch, MagicMock

from backend.integrations.fb_client import get_insights, apply_recommendation, FacebookAPIError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACCOUNT_ID = "act_123456789"
CAMPAIGN_ID = "123456789"
ACCESS_TOKEN = "test_token"
FIELDS = "campaign_id,impressions,clicks,spend,date_start,date_stop"
DATE_RANGE = {"since": "2024-01-01", "until": "2024-01-31"}

INSIGHTS_URL = f"https://graph.facebook.com/v18.0/{ACCOUNT_ID}/insights"
CAMPAIGN_URL = f"https://graph.facebook.com/v18.0/{CAMPAIGN_ID}"


def _mock_response(status_code: int, body: dict) -> MagicMock:
    """Build a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = status_code < 400
    mock.json.return_value = body
    mock.text = json.dumps(body)
    return mock


# ---------------------------------------------------------------------------
# get_insights tests
# ---------------------------------------------------------------------------

class TestGetInsights:

    def test_get_insights_success(self):
        """200 response returns dict with 'data' and 'paging' keys."""
        body = {
            "data": [{"campaign_id": "1", "impressions": "1000", "clicks": "50"}],
            "paging": {"cursors": {"before": "abc", "after": "def"}},
        }
        with patch("backend.integrations.fb_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, body)

            result = get_insights(ACCOUNT_ID, DATE_RANGE, ACCESS_TOKEN, FIELDS)

        assert "data" in result
        assert "paging" in result
        assert result["data"] == body["data"]

    def test_get_insights_rate_limit(self):
        """429 response raises FacebookAPIError with status_code=429."""
        body = {"error": {"message": "Rate limit exceeded"}}
        with patch("backend.integrations.fb_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(429, body)

            with pytest.raises(FacebookAPIError) as exc_info:
                get_insights(ACCOUNT_ID, DATE_RANGE, ACCESS_TOKEN, FIELDS)

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.message

    def test_get_insights_expired_token(self):
        """401 response raises FacebookAPIError with status_code=401."""
        body = {"error": {"message": "Invalid OAuth access token"}}
        with patch("backend.integrations.fb_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(401, body)

            with pytest.raises(FacebookAPIError) as exc_info:
                get_insights(ACCOUNT_ID, DATE_RANGE, ACCESS_TOKEN, FIELDS)

        assert exc_info.value.status_code == 401
        assert "Invalid OAuth access token" in exc_info.value.message

    def test_get_insights_network_error(self):
        """ConnectionError from requests propagates unchanged."""
        with patch("backend.integrations.fb_client.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

            with pytest.raises(requests.exceptions.ConnectionError):
                get_insights(ACCOUNT_ID, DATE_RANGE, ACCESS_TOKEN, FIELDS)

    def test_get_insights_with_pagination_cursor(self):
        """When 'after' cursor is provided it is included in the request params."""
        body = {
            "data": [{"campaign_id": "2", "impressions": "500"}],
            "paging": {"cursors": {"before": "xyz", "after": "uvw"}},
        }
        cursor = "some_cursor_value"
        with patch("backend.integrations.fb_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, body)

            get_insights(ACCOUNT_ID, DATE_RANGE, ACCESS_TOKEN, FIELDS, after=cursor)

        _, kwargs = mock_get.call_args
        sent_params = kwargs.get("params", mock_get.call_args[0][1] if len(mock_get.call_args[0]) > 1 else {})
        assert sent_params.get("after") == cursor


# ---------------------------------------------------------------------------
# apply_recommendation tests
# ---------------------------------------------------------------------------

class TestApplyRecommendation:

    def test_apply_recommendation_success(self):
        """200 POST response returns True."""
        body = {"success": True}
        with patch("backend.integrations.fb_client.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, body)

            result = apply_recommendation(CAMPAIGN_ID, {"daily_budget": 5000}, ACCESS_TOKEN)

        assert result is True

    def test_apply_recommendation_failure(self):
        """400 POST response raises FacebookAPIError."""
        body = {"error": {"message": "Invalid parameter: daily_budget"}}
        with patch("backend.integrations.fb_client.requests.post") as mock_post:
            mock_post.return_value = _mock_response(400, body)

            with pytest.raises(FacebookAPIError) as exc_info:
                apply_recommendation(CAMPAIGN_ID, {"daily_budget": -1}, ACCESS_TOKEN)

        assert exc_info.value.status_code == 400
        assert "Invalid parameter" in exc_info.value.message

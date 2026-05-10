"""
tests/test_integration_api.py — Integration tests for API Gateway → Lambda → DynamoDB round-trip.

Tests the full API round-trip using FastAPI TestClient with moto-backed DynamoDB.
Covers:
- Unauthenticated requests (no token, invalid token, expired token)
- Role-based access control (Viewer, Analyst, Admin)
- Dashboard KPI aggregation from DynamoDB
- Alert config create-and-retrieve round-trip

Requirements: 1.3, 1.4, 1.5, 1.6, 1.7
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

# ---------------------------------------------------------------------------
# Environment setup — must happen BEFORE importing the app
# ---------------------------------------------------------------------------

os.environ["TEST_MODE"] = "1"
os.environ["JWT_SECRET"] = "test-secret-key-for-unit-tests"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["DYNAMODB_METRICS_TABLE"] = "CampaignMetrics"
os.environ["DYNAMODB_RECOMMENDATIONS_TABLE"] = "Recommendations"
os.environ["DYNAMODB_ALERT_CONFIGS_TABLE"] = "AlertConfigs"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"

from jose import jwt as jose_jwt  # noqa: E402

from backend.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# TestClient — raise_server_exceptions=False so 5xx responses are returned
# as HTTP responses rather than propagated exceptions.
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-unit-tests"
JWT_ALGORITHM = "HS256"


def _make_token(
    role: str,
    username: str = "user@example.com",
    expired: bool = False,
) -> str:
    """Create a signed HS256 JWT for the given role."""
    now = datetime.now(tz=timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    payload = {
        "sub": username,
        "email": username,
        "role": role,
        "custom:role": role,
        "iat": now,
        "exp": exp,
    }
    return jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _auth_headers(
    role: str,
    username: str = "user@example.com",
    expired: bool = False,
) -> dict:
    """Return an Authorization header dict for the given role."""
    return {"Authorization": f"Bearer {_make_token(role, username=username, expired=expired)}"}


def _viewer_headers(username: str = "viewer@example.com") -> dict:
    return _auth_headers("viewer", username=username)


def _analyst_headers(username: str = "analyst@example.com") -> dict:
    return _auth_headers("analyst", username=username)


def _admin_headers(username: str = "admin@example.com") -> dict:
    return _auth_headers("admin", username=username)


# ---------------------------------------------------------------------------
# Fixtures — moto-backed DynamoDB tables
# ---------------------------------------------------------------------------


@pytest.fixture
def aws_credentials():
    """Ensure moto uses fake credentials."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def dynamodb_tables(aws_credentials):
    """
    Create all required DynamoDB tables using moto.

    Tables:
      - CampaignMetrics  (PK: campaign_id, SK: date)
      - Recommendations  (PK: campaign_id, SK: generated_at)
      - AlertConfigs     (PK: user_id, SK: campaign_id_metric)
    """
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")

        # CampaignMetrics table
        ddb.create_table(
            TableName="CampaignMetrics",
            KeySchema=[
                {"AttributeName": "campaign_id", "KeyType": "HASH"},
                {"AttributeName": "date", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "campaign_id", "AttributeType": "S"},
                {"AttributeName": "date", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Recommendations table
        ddb.create_table(
            TableName="Recommendations",
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

        # AlertConfigs table — SK is campaign_id_metric (campaign_id#metric)
        ddb.create_table(
            TableName="AlertConfigs",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "campaign_id_metric", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "campaign_id_metric", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield ddb


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_metrics(
    ddb,
    campaign_id: str = "camp_001",
    date: str = "2024-01-15",
    campaign_name: str = "Test Campaign",
) -> None:
    """Insert a CampaignMetrics record into the moto-backed table."""
    table = ddb.Table("CampaignMetrics")
    table.put_item(
        Item={
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "date": date,
            "impressions": 10000,
            "clicks": 500,
            "spend": Decimal("250.00"),
            "conversions": 25,
            "ctr": Decimal("0.05"),
            "cpc": Decimal("0.50"),
            "roas": Decimal("3.2"),
            "reach": 8000,
            "frequency": Decimal("1.25"),
        }
    )


def _seed_recommendation(
    ddb,
    campaign_id: str = "camp_001",
    generated_at: str = "2024-01-15T12:00:00",
    recommendation_id: str = "rec_001",
) -> None:
    """Insert a Recommendation record into the moto-backed table."""
    table = ddb.Table("Recommendations")
    table.put_item(
        Item={
            "campaign_id": campaign_id,
            "generated_at": generated_at,
            "recommendation_id": recommendation_id,
            "goal": "CTR",
            "action": "increase_bid",
            "current_value": Decimal("0.05"),
            "suggested_value": Decimal("0.055"),
            "confidence_score": Decimal("0.85"),
            "reasoning": "Increase bid to improve CTR",
            "applied": False,
        }
    )


# ===========================================================================
# 1. Unauthenticated requests
# ===========================================================================


class TestUnauthenticatedRequests:
    """
    Verify that protected endpoints reject requests without a valid JWT.
    Requirements: 1.3, 1.8
    """

    def test_no_token_returns_401(self):
        """GET /campaigns with no Authorization header must return 401."""
        resp = client.get("/campaigns")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        """GET /campaigns with a malformed token must return 401."""
        resp = client.get(
            "/campaigns",
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self):
        """GET /campaigns with an expired JWT must return 401."""
        resp = client.get("/campaigns", headers=_auth_headers("viewer", expired=True))
        assert resp.status_code == 401

    def test_no_token_on_metrics_returns_401(self):
        """GET /campaigns/{id}/metrics with no token must return 401."""
        resp = client.get("/campaigns/camp_001/metrics")
        assert resp.status_code == 401

    def test_no_token_on_dashboard_returns_401(self):
        """GET /dashboard/summary with no token must return 401."""
        resp = client.get("/dashboard/summary")
        assert resp.status_code == 401

    def test_no_token_on_alerts_returns_401(self):
        """GET /alerts with no token must return 401."""
        resp = client.get("/alerts")
        assert resp.status_code == 401


# ===========================================================================
# 2. Viewer role access
# ===========================================================================


class TestViewerRoleAccess:
    """
    Viewer can read campaigns, metrics, and dashboard but cannot write.
    Requirements: 1.4, 1.5
    """

    def test_viewer_can_get_campaigns(self, dynamodb_tables):
        """Viewer JWT → GET /campaigns → 200."""
        resp = client.get("/campaigns", headers=_viewer_headers())
        assert resp.status_code == 200

    def test_viewer_can_get_campaign_metrics(self, dynamodb_tables):
        """Viewer JWT → GET /campaigns/{id}/metrics → 200."""
        resp = client.get("/campaigns/camp_001/metrics", headers=_viewer_headers())
        assert resp.status_code == 200

    def test_viewer_cannot_apply_recommendation(self, dynamodb_tables):
        """Viewer JWT → POST /campaigns/{id}/apply → 403.
        Requirements: 1.5
        """
        resp = client.post(
            "/campaigns/camp_001/apply",
            json={"recommendation_id": "rec_001", "update_payload": {}},
            headers=_viewer_headers(),
        )
        assert resp.status_code == 403

    def test_viewer_cannot_post_alerts(self, dynamodb_tables):
        """Viewer JWT → POST /alerts → 403.
        Requirements: 1.5
        """
        resp = client.post(
            "/alerts",
            json={
                "user_id": "viewer@example.com",
                "campaign_id": "camp_001",
                "metric": "ctr",
                "threshold": 0.02,
                "direction": "below",
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
            },
            headers=_viewer_headers(username="viewer@example.com"),
        )
        assert resp.status_code == 403

    def test_viewer_cannot_trigger_fetch(self, dynamodb_tables):
        """Viewer JWT → POST /campaigns/fetch → 403.
        Requirements: 1.5
        """
        resp = client.post(
            "/campaigns/fetch",
            json={
                "account_id": "act_123",
                "date_range": {"since": "2024-01-01", "until": "2024-01-15"},
            },
            headers=_viewer_headers(),
        )
        assert resp.status_code == 403

    def test_viewer_cannot_get_recommendations(self, dynamodb_tables):
        """Viewer JWT → GET /campaigns/{id}/recommendations → 403.
        Requirements: 1.5
        """
        resp = client.get(
            "/campaigns/camp_001/recommendations",
            headers=_viewer_headers(),
        )
        assert resp.status_code == 403


# ===========================================================================
# 3. Analyst role access
# ===========================================================================


class TestAnalystRoleAccess:
    """
    Analyst can read and write campaigns, recommendations, and alerts.
    Requirements: 1.4, 1.6
    """

    def test_analyst_can_get_recommendations(self, dynamodb_tables):
        """Analyst JWT → GET /campaigns/{id}/recommendations → 200.
        Requirements: 1.6
        """
        resp = client.get(
            "/campaigns/camp_001/recommendations",
            headers=_analyst_headers(),
        )
        assert resp.status_code == 200

    def test_analyst_can_apply_recommendation(self, dynamodb_tables):
        """Analyst JWT → POST /campaigns/{id}/apply → 200 (Facebook API mocked).
        Requirements: 1.6
        """
        _seed_recommendation(dynamodb_tables)
        with (
            patch("backend.routes.campaigns._get_fb_access_token") as mock_token,
            patch("backend.routes.campaigns.apply_recommendation") as mock_apply,
        ):
            mock_token.return_value = "fake-fb-token"
            mock_apply.return_value = True
            resp = client.post(
                "/campaigns/camp_001/apply",
                json={
                    "recommendation_id": "rec_001",
                    "update_payload": {"daily_budget": 5000},
                },
                headers=_analyst_headers(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "applied"
        assert data["recommendation_id"] == "rec_001"

    def test_analyst_can_create_alert(self, dynamodb_tables):
        """Analyst JWT → POST /alerts → 200.
        Requirements: 1.6, 1.7
        """
        resp = client.post(
            "/alerts",
            json={
                "user_id": "analyst@example.com",
                "campaign_id": "camp_001",
                "metric": "ctr",
                "threshold": 0.02,
                "direction": "below",
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
            },
            headers=_analyst_headers(username="analyst@example.com"),
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["status"] == "saved"

    def test_analyst_can_trigger_fetch(self, dynamodb_tables):
        """Analyst JWT → POST /campaigns/fetch → 202 (fetch_and_store mocked).
        Requirements: 1.6
        """
        with patch("backend.routes.campaigns.fetch_and_store") as mock_fetch:
            mock_fetch.return_value = "raw/2024-01-15/act_123.json"
            resp = client.post(
                "/campaigns/fetch",
                json={
                    "account_id": "act_123",
                    "date_range": {"since": "2024-01-15", "until": "2024-01-15"},
                },
                headers=_analyst_headers(),
            )
        assert resp.status_code == 202
        assert resp.json()["s3_key"] == "raw/2024-01-15/act_123.json"

    def test_analyst_can_list_campaigns(self, dynamodb_tables):
        """Analyst JWT → GET /campaigns → 200."""
        resp = client.get("/campaigns", headers=_analyst_headers())
        assert resp.status_code == 200

    def test_analyst_can_get_alerts(self, dynamodb_tables):
        """Analyst JWT → GET /alerts → 200."""
        resp = client.get("/alerts", headers=_analyst_headers(username="analyst@example.com"))
        assert resp.status_code == 200


# ===========================================================================
# 4. Admin role access
# ===========================================================================


class TestAdminRoleAccess:
    """
    Admin has full access to all endpoints.
    Requirements: 1.4, 1.7
    """

    def test_admin_can_list_campaigns(self, dynamodb_tables):
        """Admin JWT → GET /campaigns → 200."""
        resp = client.get("/campaigns", headers=_admin_headers())
        assert resp.status_code == 200

    def test_admin_can_get_metrics(self, dynamodb_tables):
        """Admin JWT → GET /campaigns/{id}/metrics → 200."""
        resp = client.get("/campaigns/camp_001/metrics", headers=_admin_headers())
        assert resp.status_code == 200

    def test_admin_can_get_recommendations(self, dynamodb_tables):
        """Admin JWT → GET /campaigns/{id}/recommendations → 200."""
        resp = client.get(
            "/campaigns/camp_001/recommendations",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200

    def test_admin_can_apply_recommendation(self, dynamodb_tables):
        """Admin JWT → POST /campaigns/{id}/apply → 200."""
        _seed_recommendation(dynamodb_tables)
        with (
            patch("backend.routes.campaigns._get_fb_access_token") as mock_token,
            patch("backend.routes.campaigns.apply_recommendation") as mock_apply,
        ):
            mock_token.return_value = "fake-fb-token"
            mock_apply.return_value = True
            resp = client.post(
                "/campaigns/camp_001/apply",
                json={
                    "recommendation_id": "rec_001",
                    "update_payload": {"daily_budget": 6000},
                },
                headers=_admin_headers(),
            )
        assert resp.status_code == 200

    def test_admin_can_create_alert(self, dynamodb_tables):
        """Admin JWT → POST /alerts → 200."""
        resp = client.post(
            "/alerts",
            json={
                "user_id": "admin@example.com",
                "campaign_id": "camp_002",
                "metric": "spend",
                "threshold": 1000.0,
                "direction": "above",
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
            },
            headers=_admin_headers(username="admin@example.com"),
        )
        assert resp.status_code in (200, 201)

    def test_admin_can_trigger_fetch(self, dynamodb_tables):
        """Admin JWT → POST /campaigns/fetch → 202."""
        with patch("backend.routes.campaigns.fetch_and_store") as mock_fetch:
            mock_fetch.return_value = "raw/2024-01-15/act_456.json"
            resp = client.post(
                "/campaigns/fetch",
                json={
                    "account_id": "act_456",
                    "date_range": {"since": "2024-01-15", "until": "2024-01-15"},
                },
                headers=_admin_headers(),
            )
        assert resp.status_code == 202

    def test_admin_can_get_dashboard_summary(self, dynamodb_tables):
        """Admin JWT → GET /dashboard/summary → 200."""
        resp = client.get("/dashboard/summary", headers=_admin_headers())
        assert resp.status_code == 200

    def test_admin_has_full_access(self, dynamodb_tables):
        """
        Verify Admin can access all major endpoints without a 401 or 403.
        Requirements: 1.7
        """
        _seed_metrics(dynamodb_tables)
        _seed_recommendation(dynamodb_tables)

        endpoints_read = [
            ("GET", "/campaigns"),
            ("GET", "/campaigns/camp_001/metrics"),
            ("GET", "/dashboard/summary"),
            ("GET", "/alerts"),
        ]
        for method, path in endpoints_read:
            resp = client.request(method, path, headers=_admin_headers(username="admin@example.com"))
            assert resp.status_code not in (401, 403), (
                f"Admin should not get {resp.status_code} on {method} {path}"
            )

        # Analyst/Admin-only read endpoint
        resp = client.get(
            "/campaigns/camp_001/recommendations",
            headers=_admin_headers(),
        )
        assert resp.status_code not in (401, 403)


# ===========================================================================
# 5. Dashboard round-trip
# ===========================================================================


class TestDashboardRoundTrip:
    """
    Verify the dashboard summary endpoint aggregates DynamoDB data correctly.
    Requirements: 1.3, 1.4
    """

    def test_dashboard_summary_returns_kpis(self, dynamodb_tables):
        """
        GET /dashboard/summary → 200 with all expected KPI fields.
        Requirements: 1.3, 1.4
        """
        _seed_metrics(dynamodb_tables, campaign_id="camp_001", date="2024-01-15")
        _seed_metrics(dynamodb_tables, campaign_id="camp_002", date="2024-01-15")

        resp = client.get("/dashboard/summary", headers=_viewer_headers())
        assert resp.status_code == 200

        data = resp.json()
        # All KPI fields must be present
        assert "campaign_count" in data
        assert "total_spend" in data
        assert "total_impressions" in data
        assert "total_clicks" in data
        assert "total_conversions" in data
        assert "avg_ctr" in data
        assert "avg_cpc" in data
        assert "avg_roas" in data

        # Values must reflect the seeded data (2 campaigns × 250 spend each)
        assert data["campaign_count"] == 2
        assert data["total_spend"] == pytest.approx(500.0, abs=0.01)
        assert data["total_impressions"] == 20000
        assert data["total_clicks"] == 1000

    def test_dashboard_summary_empty_returns_zeros(self, dynamodb_tables):
        """GET /dashboard/summary with no data → 200 with zero KPIs."""
        resp = client.get("/dashboard/summary", headers=_viewer_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_count"] == 0
        assert data["total_spend"] == 0.0
        assert data["total_impressions"] == 0

    def test_campaigns_list_returns_metrics(self, dynamodb_tables):
        """
        GET /campaigns → 200 with campaign data from DynamoDB.
        Requirements: 1.3, 1.4
        """
        _seed_metrics(dynamodb_tables, campaign_id="camp_001", date="2024-01-15")
        _seed_metrics(dynamodb_tables, campaign_id="camp_002", date="2024-01-15")

        resp = client.get("/campaigns", headers=_viewer_headers())
        assert resp.status_code == 200

        data = resp.json()
        assert len(data) == 2

        campaign_ids = {item["campaign_id"] for item in data}
        assert "camp_001" in campaign_ids
        assert "camp_002" in campaign_ids

        # Each item must have the core metric fields
        for item in data:
            assert "campaign_id" in item
            assert "date" in item
            assert "impressions" in item
            assert "clicks" in item

    def test_campaigns_list_returns_latest_per_campaign(self, dynamodb_tables):
        """
        When multiple dates exist for a campaign, only the latest is returned.
        """
        _seed_metrics(dynamodb_tables, campaign_id="camp_001", date="2024-01-10")
        _seed_metrics(dynamodb_tables, campaign_id="camp_001", date="2024-01-15")

        resp = client.get("/campaigns", headers=_viewer_headers())
        assert resp.status_code == 200

        data = resp.json()
        assert len(data) == 1
        assert data[0]["date"] == "2024-01-15"

    def test_dashboard_accessible_by_all_roles(self, dynamodb_tables):
        """Dashboard summary is accessible by Viewer, Analyst, and Admin."""
        for headers in [_viewer_headers(), _analyst_headers(), _admin_headers()]:
            resp = client.get("/dashboard/summary", headers=headers)
            assert resp.status_code == 200


# ===========================================================================
# 6. Alert config round-trip
# ===========================================================================


class TestAlertConfigRoundTrip:
    """
    Verify the full create-and-retrieve round-trip for alert configurations.
    Requirements: 1.6, 1.7
    """

    def test_create_and_retrieve_alert_config(self, dynamodb_tables):
        """
        POST /alerts then GET /alerts → config appears in list.
        Requirements: 1.7
        """
        alert_payload = {
            "user_id": "analyst@example.com",
            "campaign_id": "camp_001",
            "metric": "ctr",
            "threshold": 0.02,
            "direction": "below",
            "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
        }
        headers = _analyst_headers(username="analyst@example.com")

        # Create the alert
        post_resp = client.post("/alerts", json=alert_payload, headers=headers)
        assert post_resp.status_code in (200, 201)
        post_data = post_resp.json()
        assert post_data["status"] == "saved"
        assert post_data["campaign_id"] == "camp_001"
        assert post_data["metric"] == "ctr"

        # Retrieve alerts for this user
        get_resp = client.get("/alerts", headers=headers)
        assert get_resp.status_code == 200

        alerts = get_resp.json()
        assert len(alerts) == 1
        assert alerts[0]["campaign_id"] == "camp_001"
        assert alerts[0]["metric"] == "ctr"
        assert alerts[0]["direction"] == "below"

    def test_create_multiple_alerts_all_retrieved(self, dynamodb_tables):
        """
        Multiple alerts for the same user are all returned by GET /alerts.
        """
        headers = _analyst_headers(username="analyst@example.com")

        for campaign_id, metric in [("camp_001", "ctr"), ("camp_002", "spend")]:
            client.post(
                "/alerts",
                json={
                    "user_id": "analyst@example.com",
                    "campaign_id": campaign_id,
                    "metric": metric,
                    "threshold": 0.02,
                    "direction": "below",
                    "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
                },
                headers=headers,
            )

        get_resp = client.get("/alerts", headers=headers)
        assert get_resp.status_code == 200
        alerts = get_resp.json()
        assert len(alerts) == 2

    def test_alert_config_upsert_idempotent(self, dynamodb_tables):
        """
        Creating the same alert twice (upsert) results in exactly one record.
        """
        alert_payload = {
            "user_id": "analyst@example.com",
            "campaign_id": "camp_001",
            "metric": "ctr",
            "threshold": 0.02,
            "direction": "below",
            "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
        }
        headers = _analyst_headers(username="analyst@example.com")

        resp1 = client.post("/alerts", json=alert_payload, headers=headers)
        resp2 = client.post("/alerts", json=alert_payload, headers=headers)

        assert resp1.status_code in (200, 201)
        assert resp2.status_code in (200, 201)

        get_resp = client.get("/alerts", headers=headers)
        assert len(get_resp.json()) == 1

    def test_alerts_scoped_to_authenticated_user(self, dynamodb_tables):
        """
        GET /alerts only returns alerts belonging to the authenticated user.
        """
        analyst_headers = _analyst_headers(username="analyst@example.com")
        admin_headers = _admin_headers(username="admin@example.com")

        # Analyst creates an alert
        client.post(
            "/alerts",
            json={
                "user_id": "analyst@example.com",
                "campaign_id": "camp_001",
                "metric": "ctr",
                "threshold": 0.02,
                "direction": "below",
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
            },
            headers=analyst_headers,
        )

        # Admin creates a different alert
        client.post(
            "/alerts",
            json={
                "user_id": "admin@example.com",
                "campaign_id": "camp_002",
                "metric": "spend",
                "threshold": 1000.0,
                "direction": "above",
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
            },
            headers=admin_headers,
        )

        # Each user should only see their own alerts
        analyst_alerts = client.get("/alerts", headers=analyst_headers).json()
        admin_alerts = client.get("/alerts", headers=admin_headers).json()

        assert len(analyst_alerts) == 1
        assert analyst_alerts[0]["campaign_id"] == "camp_001"

        assert len(admin_alerts) == 1
        assert admin_alerts[0]["campaign_id"] == "camp_002"

    def test_viewer_cannot_create_alert_config(self, dynamodb_tables):
        """
        Viewer JWT → POST /alerts → 403 (write operation denied).
        Requirements: 1.5
        """
        resp = client.post(
            "/alerts",
            json={
                "user_id": "viewer@example.com",
                "campaign_id": "camp_001",
                "metric": "ctr",
                "threshold": 0.02,
                "direction": "below",
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
            },
            headers=_viewer_headers(username="viewer@example.com"),
        )
        assert resp.status_code == 403

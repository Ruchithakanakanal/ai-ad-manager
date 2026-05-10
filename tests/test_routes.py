"""
tests/test_routes.py — Unit tests for API route handlers.

Tests cover:
- Auth flow (login success, invalid credentials → 401)
- JWT middleware (missing token → 401, expired token → 401)
- Role enforcement (Viewer → 403 on write endpoints, Analyst/Admin → 200)
- Campaign endpoints (list, metrics, recommendations, apply, fetch)
- Dashboard summary endpoint
- Alert config endpoints (GET, POST)

DynamoDB is mocked with moto; Facebook API is mocked with unittest.mock.
"""

import json
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

client = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-unit-tests"
JWT_ALGORITHM = "HS256"


def _make_token(role: str, username: str = "user@example.com", expired: bool = False) -> str:
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


def _auth_headers(role: str, expired: bool = False, username: str = "user@example.com") -> dict:
    return {"Authorization": f"Bearer {_make_token(role, username=username, expired=expired)}"}


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
    """Create all required DynamoDB tables using moto."""
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

        # AlertConfigs table
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
# Helper: seed DynamoDB with sample data
# ---------------------------------------------------------------------------


def _seed_metrics(ddb, campaign_id: str = "camp_001", date: str = "2024-01-15"):
    table = ddb.Table("CampaignMetrics")
    table.put_item(
        Item={
            "campaign_id": campaign_id,
            "campaign_name": "Test Campaign",
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


def _seed_recommendation(ddb, campaign_id: str = "camp_001"):
    table = ddb.Table("Recommendations")
    table.put_item(
        Item={
            "campaign_id": campaign_id,
            "generated_at": "2024-01-15T12:00:00",
            "recommendation_id": "rec_001",
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
# 1. Auth endpoint tests
# ===========================================================================


class TestAuthLogin:
    def test_login_valid_viewer(self):
        resp = client.post(
            "/auth/login",
            json={"username": "viewer@example.com", "password": "viewerpass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"

    def test_login_valid_analyst(self):
        resp = client.post(
            "/auth/login",
            json={"username": "analyst@example.com", "password": "analystpass"},
        )
        assert resp.status_code == 200
        payload = jose_jwt.decode(
            resp.json()["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        assert payload["role"] == "analyst"

    def test_login_valid_admin(self):
        resp = client.post(
            "/auth/login",
            json={"username": "admin@example.com", "password": "adminpass"},
        )
        assert resp.status_code == 200
        payload = jose_jwt.decode(
            resp.json()["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        assert payload["role"] == "admin"

    def test_login_wrong_password_returns_401(self):
        resp = client.post(
            "/auth/login",
            json={"username": "viewer@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_unknown_user_returns_401(self):
        resp = client.post(
            "/auth/login",
            json={"username": "nobody@example.com", "password": "pass"},
        )
        assert resp.status_code == 401

    def test_login_missing_fields_returns_422(self):
        resp = client.post("/auth/login", json={"username": "viewer@example.com"})
        assert resp.status_code == 422


# ===========================================================================
# 2. JWT middleware tests
# ===========================================================================


class TestJWTMiddleware:
    def test_missing_token_returns_401(self):
        resp = client.get("/campaigns")
        assert resp.status_code == 401

    def test_malformed_token_returns_401(self):
        resp = client.get(
            "/campaigns", headers={"Authorization": "Bearer not.a.valid.jwt"}
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self):
        resp = client.get("/campaigns", headers=_auth_headers("viewer", expired=True))
        assert resp.status_code == 401

    def test_valid_token_passes_middleware(self, dynamodb_tables):
        resp = client.get("/campaigns", headers=_auth_headers("viewer"))
        # Should not be 401 (may be 200 or 500 depending on DynamoDB state)
        assert resp.status_code != 401

    def test_public_path_no_auth_required(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_login_path_no_auth_required(self):
        resp = client.post(
            "/auth/login",
            json={"username": "viewer@example.com", "password": "viewerpass"},
        )
        assert resp.status_code == 200


# ===========================================================================
# 3. Campaign endpoints — role enforcement
# ===========================================================================


class TestCampaignRoleEnforcement:
    """Viewer can read; Analyst/Admin can read and write."""

    def test_viewer_can_list_campaigns(self, dynamodb_tables):
        resp = client.get("/campaigns", headers=_auth_headers("viewer"))
        assert resp.status_code == 200

    def test_viewer_can_get_metrics(self, dynamodb_tables):
        resp = client.get("/campaigns/camp_001/metrics", headers=_auth_headers("viewer"))
        assert resp.status_code == 200

    def test_viewer_cannot_get_recommendations(self, dynamodb_tables):
        """Viewer should receive 403 on recommendations endpoint."""
        resp = client.get(
            "/campaigns/camp_001/recommendations", headers=_auth_headers("viewer")
        )
        assert resp.status_code == 403

    def test_analyst_can_get_recommendations(self, dynamodb_tables):
        resp = client.get(
            "/campaigns/camp_001/recommendations", headers=_auth_headers("analyst")
        )
        assert resp.status_code == 200

    def test_admin_can_get_recommendations(self, dynamodb_tables):
        resp = client.get(
            "/campaigns/camp_001/recommendations", headers=_auth_headers("admin")
        )
        assert resp.status_code == 200

    def test_viewer_cannot_trigger_fetch(self, dynamodb_tables):
        resp = client.post(
            "/campaigns/fetch",
            json={"account_id": "act_123", "date_range": {"since": "2024-01-01", "until": "2024-01-15"}},
            headers=_auth_headers("viewer"),
        )
        assert resp.status_code == 403

    def test_viewer_cannot_apply_recommendation(self, dynamodb_tables):
        resp = client.post(
            "/campaigns/camp_001/apply",
            json={"recommendation_id": "rec_001", "update_payload": {"daily_budget": 5000}},
            headers=_auth_headers("viewer"),
        )
        assert resp.status_code == 403

    def test_analyst_can_trigger_fetch(self, dynamodb_tables):
        """Analyst can trigger fetch; it will fail at the FB API level (mocked)."""
        with patch("backend.routes.campaigns.fetch_and_store") as mock_fetch:
            mock_fetch.return_value = "raw/2024-01-15/act_123.json"
            resp = client.post(
                "/campaigns/fetch",
                json={
                    "account_id": "act_123",
                    "date_range": {"since": "2024-01-15", "until": "2024-01-15"},
                },
                headers=_auth_headers("analyst"),
            )
        assert resp.status_code == 202
        assert resp.json()["s3_key"] == "raw/2024-01-15/act_123.json"

    def test_admin_can_trigger_fetch(self, dynamodb_tables):
        with patch("backend.routes.campaigns.fetch_and_store") as mock_fetch:
            mock_fetch.return_value = "raw/2024-01-15/act_456.json"
            resp = client.post(
                "/campaigns/fetch",
                json={
                    "account_id": "act_456",
                    "date_range": {"since": "2024-01-15", "until": "2024-01-15"},
                },
                headers=_auth_headers("admin"),
            )
        assert resp.status_code == 202


# ===========================================================================
# 4. Campaign data endpoints — functional tests
# ===========================================================================


class TestCampaignEndpoints:
    def test_list_campaigns_empty(self, dynamodb_tables):
        resp = client.get("/campaigns", headers=_auth_headers("viewer"))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_campaigns_with_data(self, dynamodb_tables):
        _seed_metrics(dynamodb_tables)
        resp = client.get("/campaigns", headers=_auth_headers("viewer"))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["campaign_id"] == "camp_001"

    def test_list_campaigns_returns_latest_per_campaign(self, dynamodb_tables):
        """When multiple dates exist, only the latest is returned per campaign."""
        _seed_metrics(dynamodb_tables, campaign_id="camp_001", date="2024-01-10")
        _seed_metrics(dynamodb_tables, campaign_id="camp_001", date="2024-01-15")
        resp = client.get("/campaigns", headers=_auth_headers("viewer"))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["date"] == "2024-01-15"

    def test_get_metrics_empty(self, dynamodb_tables):
        resp = client.get("/campaigns/nonexistent/metrics", headers=_auth_headers("viewer"))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_metrics_with_data(self, dynamodb_tables):
        _seed_metrics(dynamodb_tables, campaign_id="camp_002", date="2024-01-10")
        _seed_metrics(dynamodb_tables, campaign_id="camp_002", date="2024-01-15")
        resp = client.get("/campaigns/camp_002/metrics", headers=_auth_headers("viewer"))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Should be sorted ascending by date
        assert data[0]["date"] == "2024-01-10"
        assert data[1]["date"] == "2024-01-15"

    def test_get_recommendations_empty(self, dynamodb_tables):
        resp = client.get(
            "/campaigns/camp_001/recommendations", headers=_auth_headers("analyst")
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_recommendations_with_data(self, dynamodb_tables):
        _seed_recommendation(dynamodb_tables)
        resp = client.get(
            "/campaigns/camp_001/recommendations", headers=_auth_headers("analyst")
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["recommendation_id"] == "rec_001"

    def test_apply_recommendation_not_found(self, dynamodb_tables):
        resp = client.post(
            "/campaigns/camp_001/apply",
            json={"recommendation_id": "nonexistent", "update_payload": {}},
            headers=_auth_headers("analyst"),
        )
        assert resp.status_code == 404

    def test_apply_recommendation_success(self, dynamodb_tables):
        _seed_recommendation(dynamodb_tables)
        with patch("backend.routes.campaigns._get_fb_access_token") as mock_token, \
             patch("backend.routes.campaigns.apply_recommendation") as mock_apply:
            mock_token.return_value = "fake-token"
            mock_apply.return_value = True
            resp = client.post(
                "/campaigns/camp_001/apply",
                json={
                    "recommendation_id": "rec_001",
                    "update_payload": {"daily_budget": 5000},
                },
                headers=_auth_headers("analyst"),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "applied"
        assert data["recommendation_id"] == "rec_001"

        # Verify DynamoDB was updated
        table = dynamodb_tables.Table("Recommendations")
        item = table.get_item(
            Key={"campaign_id": "camp_001", "generated_at": "2024-01-15T12:00:00"}
        )["Item"]
        assert item["applied"] is True

    def test_apply_recommendation_facebook_error(self, dynamodb_tables):
        _seed_recommendation(dynamodb_tables)
        from backend.integrations.fb_client import FacebookAPIError

        with patch("backend.routes.campaigns._get_fb_access_token") as mock_token, \
             patch("backend.routes.campaigns.apply_recommendation") as mock_apply:
            mock_token.return_value = "fake-token"
            mock_apply.side_effect = FacebookAPIError(400, "Invalid campaign")
            resp = client.post(
                "/campaigns/camp_001/apply",
                json={
                    "recommendation_id": "rec_001",
                    "update_payload": {"daily_budget": 5000},
                },
                headers=_auth_headers("analyst"),
            )
        assert resp.status_code == 502


# ===========================================================================
# 5. Dashboard summary endpoint
# ===========================================================================


class TestDashboardSummary:
    def test_summary_no_auth_returns_401(self):
        resp = client.get("/dashboard/summary")
        assert resp.status_code == 401

    def test_summary_empty_returns_zeros(self, dynamodb_tables):
        resp = client.get("/dashboard/summary", headers=_auth_headers("viewer"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_count"] == 0
        assert data["total_spend"] == 0.0

    def test_summary_with_data(self, dynamodb_tables):
        _seed_metrics(dynamodb_tables, campaign_id="camp_001", date="2024-01-15")
        _seed_metrics(dynamodb_tables, campaign_id="camp_002", date="2024-01-15")
        resp = client.get("/dashboard/summary", headers=_auth_headers("viewer"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_count"] == 2
        assert data["total_impressions"] == 20000
        assert data["total_clicks"] == 1000

    def test_summary_viewer_can_access(self, dynamodb_tables):
        resp = client.get("/dashboard/summary", headers=_auth_headers("viewer"))
        assert resp.status_code == 200

    def test_summary_analyst_can_access(self, dynamodb_tables):
        resp = client.get("/dashboard/summary", headers=_auth_headers("analyst"))
        assert resp.status_code == 200

    def test_summary_admin_can_access(self, dynamodb_tables):
        resp = client.get("/dashboard/summary", headers=_auth_headers("admin"))
        assert resp.status_code == 200


# ===========================================================================
# 6. Alert config endpoints
# ===========================================================================


class TestAlertEndpoints:
    def test_get_alerts_no_auth_returns_401(self):
        resp = client.get("/alerts")
        assert resp.status_code == 401

    def test_get_alerts_empty(self, dynamodb_tables):
        resp = client.get("/alerts", headers=_auth_headers("analyst", ))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_viewer_cannot_create_alert(self, dynamodb_tables):
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
            headers=_auth_headers("viewer"),
        )
        assert resp.status_code == 403

    def test_analyst_can_create_alert(self, dynamodb_tables):
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
            headers=_auth_headers("analyst", username="analyst@example.com"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert data["campaign_id"] == "camp_001"

    def test_admin_can_create_alert(self, dynamodb_tables):
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
            headers=_auth_headers("admin", username="admin@example.com"),
        )
        assert resp.status_code == 200

    def test_create_and_retrieve_alert(self, dynamodb_tables):
        """Alert created via POST should be returned by GET."""
        # Create alert
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
            headers=_auth_headers("analyst", username="analyst@example.com"),
        )

        # Retrieve alerts for this user
        resp = client.get(
            "/alerts",
            headers=_auth_headers("analyst", username="analyst@example.com"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["campaign_id"] == "camp_001"
        assert data[0]["metric"] == "ctr"
        assert data[0]["direction"] == "below"

    def test_create_alert_idempotent(self, dynamodb_tables):
        """Creating the same alert twice should succeed (upsert)."""
        alert_data = {
            "user_id": "analyst@example.com",
            "campaign_id": "camp_001",
            "metric": "ctr",
            "threshold": 0.02,
            "direction": "below",
            "sns_topic_arn": "arn:aws:sns:us-east-1:123456789:alerts",
        }
        headers = _auth_headers("analyst", username="analyst@example.com")

        resp1 = client.post("/alerts", json=alert_data, headers=headers)
        resp2 = client.post("/alerts", json=alert_data, headers=headers)

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        # Should still be only one record
        resp = client.get("/alerts", headers=headers)
        assert len(resp.json()) == 1


# ===========================================================================
# 7. Token claim extraction
# ===========================================================================


class TestTokenClaims:
    def test_custom_role_claim_extracted(self):
        """JWT with custom:role claim should be accepted."""
        from backend.auth_utils import decode_token, get_role

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "user123",
            "custom:role": "analyst",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        token = jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        decoded = decode_token(token)
        assert get_role(decoded) == "analyst"

    def test_role_claim_extracted(self):
        """JWT with plain role claim should be accepted."""
        from backend.auth_utils import decode_token, get_role

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "user123",
            "role": "admin",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        token = jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        decoded = decode_token(token)
        assert get_role(decoded) == "admin"

    def test_missing_role_defaults_to_viewer(self):
        """JWT without any role claim defaults to viewer."""
        from backend.auth_utils import decode_token, get_role

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "user123",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        token = jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        decoded = decode_token(token)
        assert get_role(decoded) == "viewer"

    def test_expired_token_raises_401(self):
        """Expired token should raise HTTPException 401."""
        from fastapi import HTTPException

        from backend.auth_utils import decode_token

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "user123",
            "role": "admin",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
        token = jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

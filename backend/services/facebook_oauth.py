"""Helpers for the per-user "Connect with Facebook" OAuth flow.

The Facebook App ID / App Secret are a one-time, app-level configuration
(read from environment variables). Individual users never touch them: they
just click "Connect Facebook" in the UI and authorize their own account.
"""

import os
from urllib.parse import urlencode

import requests

GRAPH_VERSION = "v22.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
DIALOG_BASE = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"

# Permissions required to read/manage Facebook ad accounts and campaigns.
DEFAULT_SCOPES = [
    "public_profile",
    "email",
    "ads_read",
    "ads_management",
    "business_management",
]


def get_app_id() -> str:
    return (os.getenv("FACEBOOK_APP_ID") or "").strip()


def get_app_secret() -> str:
    return (os.getenv("FACEBOOK_APP_SECRET") or "").strip()


def is_configured() -> bool:
    """True when the backend has a Facebook App ID + Secret configured."""
    return bool(get_app_id() and get_app_secret())


def build_login_url(state: str, redirect_uri: str) -> str:
    """Build the Facebook OAuth dialog URL the user is sent to."""
    params = {
        "client_id": get_app_id(),
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "scope": ",".join(DEFAULT_SCOPES),
    }
    return f"{DIALOG_BASE}?{urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> str:
    """Exchange an OAuth ``code`` for a short-lived user access token."""
    resp = requests.get(
        f"{GRAPH_BASE}/oauth/access_token",
        params={
            "client_id": get_app_id(),
            "client_secret": get_app_secret(),
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok or "access_token" not in data:
        raise ValueError(data.get("error", {}).get("message", "Token exchange failed"))
    return data["access_token"]


def get_long_lived_token(short_token: str) -> str:
    """Exchange a short-lived token for a long-lived one (best effort)."""
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": get_app_id(),
                "client_secret": get_app_secret(),
                "fb_exchange_token": short_token,
            },
            timeout=30,
        )
        data = resp.json()
        if resp.ok and "access_token" in data:
            return data["access_token"]
    except requests.RequestException:
        pass
    return short_token


def fetch_user_profile(access_token: str) -> dict:
    """Fetch the connected Facebook user's id + name."""
    resp = requests.get(
        f"{GRAPH_BASE}/me",
        params={"fields": "id,name,email", "access_token": access_token},
        timeout=30,
    )
    data = resp.json()
    if not resp.ok:
        raise ValueError(data.get("error", {}).get("message", "Failed to fetch profile"))
    return data


def fetch_ad_accounts(access_token: str) -> list:
    """Fetch the ad accounts the connected user can manage."""
    resp = requests.get(
        f"{GRAPH_BASE}/me/adaccounts",
        params={
            "fields": "id,account_id,name,account_status,currency",
            "access_token": access_token,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok:
        return []
    return data.get("data", [])

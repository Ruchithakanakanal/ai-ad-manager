"""SQLAlchemy model storing each user's connected Facebook account.

A row is created/updated when a user completes the "Connect with Facebook"
OAuth flow. Tokens are stored per application user (keyed by ``user_key``)
so that different logins can connect different Facebook business accounts
entirely from the frontend, without editing backend env files.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FacebookConnection(Base):
    __tablename__ = "facebook_connections"

    id = Column(Integer, primary_key=True, index=True)

    # Identifies the logged-in application user (JWT "sub"/email, lowercased).
    user_key = Column(String, unique=True, index=True, nullable=False)

    # Facebook user/business details returned by the Graph API.
    fb_user_id = Column(String, nullable=True)
    fb_user_name = Column(String, nullable=True)

    # OAuth access token for this user's Facebook account.
    access_token = Column(Text, nullable=False)

    # Currently selected ad account plus the full list (JSON string).
    ad_account_id = Column(String, nullable=True)
    ad_accounts = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

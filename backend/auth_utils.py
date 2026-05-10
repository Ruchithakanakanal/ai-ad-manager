"""
auth_utils.py — JWT validation and role-based access helpers.

Decodes and validates Cognito JWTs (or test JWTs signed with a local secret).
Provides FastAPI dependency functions for authentication and role enforcement.
"""

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from jose import JWTError, jwt as jose_jwt
    _JOSE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JOSE_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# In production this is the Cognito User Pool's JWKS endpoint; for tests we
# use a symmetric HS256 secret so no network call is needed.
JWT_SECRET = os.environ.get("JWT_SECRET", "test-secret-key-for-unit-tests")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# Role constants
ROLE_VIEWER = "viewer"
ROLE_ANALYST = "analyst"
ROLE_ADMIN = "admin"

WRITE_ROLES = {ROLE_ANALYST, ROLE_ADMIN}
ALL_ROLES = {ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN}

# ---------------------------------------------------------------------------
# Bearer scheme (auto_error=False so we can return a custom 401)
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.

    Uses python-jose with HS256 by default (suitable for tests).
    In production, swap the secret/algorithm for Cognito RS256 JWKS.

    Raises:
        HTTPException 401: if the token is missing, malformed, or expired.
    """
    try:
        payload = jose_jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI dependency: get current user payload
# ---------------------------------------------------------------------------


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency that validates the Bearer JWT and returns the payload.

    Returns the decoded JWT payload dict (includes 'sub', 'role', etc.).

    Raises:
        HTTPException 401: if no token is provided or the token is invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(credentials.credentials)


# ---------------------------------------------------------------------------
# Role extraction helper
# ---------------------------------------------------------------------------


def get_role(payload: dict) -> str:
    """Extract the role claim from a decoded JWT payload.

    Checks both ``custom:role`` (Cognito custom attribute) and ``role``.
    Defaults to ``viewer`` if neither is present.
    """
    return payload.get("custom:role") or payload.get("role") or ROLE_VIEWER


# ---------------------------------------------------------------------------
# Role-enforcement dependencies
# ---------------------------------------------------------------------------


def require_analyst_or_admin(payload: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency that requires Analyst or Admin role.

    Raises:
        HTTPException 403: if the authenticated user is a Viewer.
    """
    role = get_role(payload)
    if role not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' does not have permission for this action",
        )
    return payload


def require_admin(payload: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency that requires Admin role.

    Raises:
        HTTPException 403: if the authenticated user is not an Admin.
    """
    role = get_role(payload)
    if role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' does not have permission for this action",
        )
    return payload

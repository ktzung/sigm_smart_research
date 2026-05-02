"""Property-based tests for protected endpoint authentication.

Validates: Requirements 3.5, 3.6
"""
import os

# Use in-memory SQLite for this test module
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_research_platform.db")

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# App + client setup
# ---------------------------------------------------------------------------

from main import app

client = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Protected paths — endpoints that require a valid JWT.
# Only paths that are actually registered AND protected are listed here.
# We use GET where available; for POST-only endpoints we use POST.
# ---------------------------------------------------------------------------

PROTECTED_PATHS = [
    # Topics — GET list requires auth
    "/api/v1/topics",
    # Labs — GET list requires auth
    "/api/v1/labs",
    # Lab usage — requires auth + professor role (auth check fires first)
    "/api/v1/labs/1/usage",
    # Lab audit — requires auth + professor role (auth check fires first)
    "/api/v1/labs/1/audit",
]

# Malformed token variants to exercise the "malformed token" branch
MALFORMED_TOKENS = [
    "not-a-jwt",
    "Bearer",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
    "a.b.c",
    "",
]


# ---------------------------------------------------------------------------
# Property 9a: No token → HTTP 401
# ---------------------------------------------------------------------------

@h_settings(max_examples=50, deadline=None)
@given(path=st.sampled_from(PROTECTED_PATHS))
def test_protected_endpoint_requires_auth_no_token(path):
    """Property 9: Protected endpoints return 401 when no token is provided.

    **Validates: Requirements 3.5, 3.6**
    """
    response = client.get(path)
    assert response.status_code == 401, (
        f"Expected 401 for {path} with no token, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Property 9b: Malformed token → HTTP 401
# ---------------------------------------------------------------------------

@h_settings(max_examples=50, deadline=None)
@given(
    path=st.sampled_from(PROTECTED_PATHS),
    token=st.sampled_from(MALFORMED_TOKENS),
)
def test_protected_endpoint_rejects_malformed_token(path, token):
    """Property 9: Protected endpoints return 401 when a malformed token is provided.

    **Validates: Requirements 3.5, 3.6**
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.get(path, headers=headers)
    assert response.status_code == 401, (
        f"Expected 401 for {path} with malformed token '{token}', got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Property 9c: Expired token → HTTP 401
# ---------------------------------------------------------------------------

def _make_expired_token() -> str:
    """Create a JWT that is already expired."""
    import uuid
    from datetime import datetime, timezone, timedelta
    from jose import jwt
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "email": "test@example.com",
        "iat": int((now - timedelta(hours=48)).timestamp()),
        "exp": int((now - timedelta(hours=24)).timestamp()),  # expired 24h ago
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@h_settings(max_examples=20, deadline=None)
@given(path=st.sampled_from(PROTECTED_PATHS))
def test_protected_endpoint_rejects_expired_token(path):
    """Property 9: Protected endpoints return 401 when an expired token is provided.

    **Validates: Requirements 3.5, 3.6**
    """
    expired_token = _make_expired_token()
    response = client.get(path, headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401, (
        f"Expected 401 for {path} with expired token, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Whitelist sanity check — public endpoints must NOT return 401
# ---------------------------------------------------------------------------

def test_health_endpoint_is_public():
    """Whitelist: /health must be accessible without auth."""
    response = client.get("/health")
    assert response.status_code == 200


def test_auth_register_is_public():
    """Whitelist: POST /api/v1/auth/register must be accessible without auth."""
    # We just check it doesn't return 401 (it may return 422 for missing body)
    response = client.post("/api/v1/auth/register")
    assert response.status_code != 401


def test_auth_login_is_public():
    """Whitelist: POST /api/v1/auth/login must be accessible without auth."""
    response = client.post("/api/v1/auth/login")
    assert response.status_code != 401

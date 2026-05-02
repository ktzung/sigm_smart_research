"""Property-based tests for authentication service.

Validates: Requirements 3.4
"""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.core.security import hash_password
from app.services.auth_service import login

KNOWN_EMAIL = "test@example.com"
KNOWN_PASSWORD = "correctpassword123"
# Pre-compute hash once to avoid bcrypt overhead on every test example
_KNOWN_PASSWORD_HASH = hash_password(KNOWN_PASSWORD)


def _make_db_with_user():
    """Return a mock DB that returns a valid user for KNOWN_EMAIL."""
    from app.models.auth import User

    user = MagicMock(spec=User)
    user.email = KNOWN_EMAIL
    user.password_hash = _KNOWN_PASSWORD_HASH
    user.is_active = True

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = user
    return db


def _make_db_no_user():
    """Return a mock DB that returns None (user not found)."""
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
    return db


@h_settings(max_examples=100, deadline=None)
@given(wrong_email=st.emails().filter(lambda e: e.lower() != KNOWN_EMAIL))
def test_wrong_email_returns_401(wrong_email):
    """Property 8: Wrong email returns HTTP 401 with 'Invalid credentials'.

    **Validates: Requirements 3.4**
    """
    db = _make_db_no_user()
    with pytest.raises(HTTPException) as exc_info:
        login(wrong_email, KNOWN_PASSWORD, db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid credentials"


@h_settings(max_examples=20, deadline=None)  # bcrypt is slow; 20 examples is sufficient
@given(wrong_password=st.text(min_size=1).filter(lambda p: p != KNOWN_PASSWORD))
def test_wrong_password_returns_401(wrong_password):
    """Property 8: Wrong password returns HTTP 401 with 'Invalid credentials'.

    **Validates: Requirements 3.4**
    """
    db = _make_db_with_user()
    with pytest.raises(HTTPException) as exc_info:
        login(KNOWN_EMAIL, wrong_password, db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid credentials"


# ── Property 6: Registration input validation ─────────────────────────────────

from app.services.auth_service import register


@h_settings(max_examples=100, deadline=None)
@given(
    email=st.emails(),
    password=st.text(max_size=7),  # too short (< 8 chars)
    display_name=st.text(min_size=1),
)
def test_short_password_rejected(email, password, display_name):
    """Property 6: Short passwords (< 8 chars) are rejected with HTTP 422.

    **Validates: Requirements 3.1**
    """
    db = _make_db_no_user()
    with pytest.raises(HTTPException) as exc_info:
        register(email, password, display_name, db)
    assert exc_info.value.status_code == 422


@h_settings(max_examples=100, deadline=None)
@given(
    email=st.emails(),
    password=st.text(min_size=8),
    display_name=st.just(""),  # empty display_name
)
def test_empty_display_name_rejected(email, password, display_name):
    """Property 6: Empty display_name is rejected with HTTP 422.

    **Validates: Requirements 3.1**
    """
    db = _make_db_no_user()
    with pytest.raises(HTTPException) as exc_info:
        register(email, password, display_name, db)
    assert exc_info.value.status_code == 422


@h_settings(max_examples=50, deadline=None)
@given(
    email=st.emails(),
    password=st.text(min_size=8),
    display_name=st.text(min_size=1).filter(lambda s: s.strip() != ""),
)
def test_valid_inputs_accepted(email, password, display_name):
    """Property 6: Valid inputs (valid email, password >= 8, non-empty display_name)
    are accepted — no exception raised, or HTTP 400 only if email already exists.

    **Validates: Requirements 3.1**
    """
    db = _make_db_no_user()
    try:
        result = register(email, password, display_name, db)
        # Success: should return a TokenPair
        assert result.access_token
        assert result.refresh_token
    except HTTPException as exc:
        # Only HTTP 400 (duplicate email) is acceptable for valid inputs
        assert exc.status_code == 400

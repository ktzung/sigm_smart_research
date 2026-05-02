"""Property-based tests for security utilities.

Validates: Requirements 3.3, 3.7
"""
import uuid

from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.core.security import create_access_token, decode_access_token, hash_password


@h_settings(max_examples=200)
@given(
    user_id=st.integers(min_value=1, max_value=10**9),
    email=st.emails(),
)
def test_jwt_expiry_exactly_24h(user_id, email):
    """Property 7: JWT access token expiry is exactly 24 hours.

    **Validates: Requirements 3.3**
    """
    jti = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, email=email, jti=jti)
    payload = decode_access_token(token)
    assert payload["exp"] - payload["iat"] == 86400


@h_settings(max_examples=50, deadline=None)  # bcrypt is slow, keep examples low
@given(password=st.text(min_size=8, max_size=72).filter(lambda p: len(p.encode("utf-8")) <= 72))
def test_bcrypt_cost_factor_at_least_12(password):
    """Property 10: Passwords stored as bcrypt with cost >= 12.

    **Validates: Requirements 3.7**
    """
    hashed = hash_password(password)
    # bcrypt format: $2b$<cost>$<salt+hash>
    assert hashed.startswith("$2b$12$") or hashed.startswith("$2b$1")
    # More precise: extract cost factor
    parts = hashed.split("$")
    cost = int(parts[2])
    assert cost >= 12

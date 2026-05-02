"""Property-based tests for profile, publication, and project validation.

Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.schemas.profile import PublicationCreate, ProjectCreate, ProfileUpdate
from app.services.profile_service import (
    VALID_PUB_TYPES,
    VALID_PROJECT_STATUSES,
    update_profile,
    get_or_create_profile,
)

# ── Property 24: Publication type validation rejects invalid values ───────────

@h_settings(max_examples=200)
@given(pub_type=st.text().filter(lambda x: x not in VALID_PUB_TYPES))
def test_invalid_pub_type_rejected(pub_type):
    """Property 24: Publication type validation rejects invalid values.

    **Validates: Requirements 6.2**
    """
    with pytest.raises((ValidationError, ValueError)):
        PublicationCreate(
            title="Test",
            authors=["Author A"],
            venue="ICML",
            year=2024,
            pub_type=pub_type,
        )


# ── Property 25: Project status validation rejects invalid values ─────────────

@h_settings(max_examples=200)
@given(status=st.text().filter(lambda x: x not in VALID_PROJECT_STATUSES))
def test_invalid_project_status_rejected(status):
    """Property 25: Project status validation rejects invalid values.

    **Validates: Requirements 6.3**
    """
    with pytest.raises((ValidationError, ValueError)):
        ProjectCreate(
            title="Test Project",
            description="A test project",
            role="PI",
            start_date=date(2024, 1, 1),
            status=status,
        )


# ── Property 29: Profile update round-trip preservation ──────────────────────

@h_settings(max_examples=100, deadline=None)
@given(
    bio=st.text(max_size=500),
    website=st.one_of(st.none(), st.text(max_size=200)),
)
def test_profile_update_roundtrip(bio, website):
    """Property 29: Profile update round-trip preservation.

    **Validates: Requirements 6.1**
    """
    from app.models.profile import UserProfile

    profile = MagicMock(spec=UserProfile)
    profile.user_id = 1
    profile.bio = None
    profile.website_url = None

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = profile
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: None)

    data = ProfileUpdate(bio=bio, website_url=website)
    result = update_profile(1, data, db)

    # After update, the profile object should have the new values set
    if bio is not None:
        assert profile.bio == bio
    if website is not None:
        assert profile.website_url == website


# ── Property 30: Cross-user profile edit is forbidden ────────────────────────

@h_settings(max_examples=100, deadline=None)
@given(
    owner_id=st.integers(min_value=1, max_value=500),
    requester_id=st.integers(min_value=501, max_value=1000),
)
def test_cross_user_profile_edit_forbidden(owner_id, requester_id):
    """Property 30: Cross-user profile edit is forbidden.

    **Validates: Requirements 6.4**
    """
    from app.services.profile_service import delete_publication
    from app.models.profile import Publication

    pub = MagicMock(spec=Publication)
    pub.id = 1
    pub.user_id = owner_id

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = pub

    with pytest.raises(HTTPException) as exc_info:
        delete_publication(requester_id, 1, db)
    assert exc_info.value.status_code == 403

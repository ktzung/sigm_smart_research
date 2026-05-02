"""Property-based tests for lab management.

Validates: Requirements 4.1, 4.2, 4.3, 4.6, 4.7, 4.8, 4.16
"""
import pytest
from unittest.mock import MagicMock
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st
from fastapi import HTTPException

from app.services.lab_service import (
    ROLE_HIERARCHY,
    VALID_ROLES,
    check_role_permission,
    create_lab,
    invite_member,
)
from app.models.lab import LabMember


@h_settings(max_examples=100, deadline=None)
@given(name=st.text(min_size=1, max_size=100))
def test_lab_creation_assigns_professor_to_owner(name):
    """Property 15: Lab creation assigns professor role to owner.

    **Validates: Requirements 4.1, 4.2**
    """
    db = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()

    owner = MagicMock()
    owner.id = 1

    added_objects = []
    db.add = lambda obj: added_objects.append(obj)

    create_lab(name, None, owner, db)

    members = [obj for obj in added_objects if isinstance(obj, LabMember)]
    assert len(members) == 1
    assert members[0].role == "professor"
    assert members[0].user_id == owner.id


@h_settings(max_examples=200)
@given(role=st.text().filter(lambda x: x not in VALID_ROLES))
def test_invalid_role_rejected(role):
    """Property 16: Lab role validation rejects invalid values.

    **Validates: Requirements 4.3**
    """
    db = MagicMock()
    inviter = MagicMock()
    inviter.id = 1

    with pytest.raises(HTTPException) as exc_info:
        invite_member(1, "test@example.com", role, inviter, db)
    assert exc_info.value.status_code == 422


@h_settings(max_examples=200)
@given(
    member_role=st.sampled_from(list(ROLE_HIERARCHY.keys())),
    required_role=st.sampled_from(list(ROLE_HIERARCHY.keys())),
)
def test_role_hierarchy_correct(member_role, required_role):
    """Property 17: Role hierarchy enforces permissions correctly.

    **Validates: Requirements 4.6, 4.7, 4.8, 4.16**
    """
    member = MagicMock()
    member.role = member_role

    result = check_role_permission(member, required_role)
    expected = ROLE_HIERARCHY[member_role] >= ROLE_HIERARCHY[required_role]
    assert result == expected

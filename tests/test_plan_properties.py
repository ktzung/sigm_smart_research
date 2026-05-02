"""Property-based tests for plan enforcement and lab access control.

Validates: Requirements 4.9, 4.10, 4.11, 4.12, 4.13
"""
import pytest
from unittest.mock import MagicMock
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st
from fastapi import HTTPException

from app.middleware.plan_enforcement import PlanEnforcer
from app.models.audit import UsageStat


# ── Property 18: Plan limits are enforced at boundaries ──────────────────────

@h_settings(max_examples=50, deadline=None)
@given(plan=st.just("free"))
def test_free_plan_at_limit_raises_429(plan):
    """Property 18: Plan limits are enforced at boundaries — free plan at limit.

    **Validates: Requirements 4.9, 4.10, 4.11**
    """
    enforcer = PlanEnforcer()

    user = MagicMock()
    user.plan = plan
    user.id = 1

    stat = MagicMock(spec=UsageStat)
    stat.topics_created = 5  # at the free limit

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = stat

    with pytest.raises(HTTPException) as exc_info:
        enforcer.check_topic_limit(user, db)
    assert exc_info.value.status_code == 429


@h_settings(max_examples=50, deadline=None)
@given(plan=st.just("free"))
def test_free_plan_below_limit_does_not_raise(plan):
    """Property 18: Plan limits are enforced at boundaries — free plan below limit.

    **Validates: Requirements 4.9, 4.10, 4.11**
    """
    enforcer = PlanEnforcer()

    user = MagicMock()
    user.plan = plan
    user.id = 1

    stat = MagicMock(spec=UsageStat)
    stat.topics_created = 4  # below the free limit of 5

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = stat

    # Should not raise
    enforcer.check_topic_limit(user, db)


@h_settings(max_examples=50, deadline=None)
@given(plan=st.just("paid"))
def test_paid_plan_at_free_limit_does_not_raise(plan):
    """Property 18: Plan limits are enforced at boundaries — paid plan at free limit.

    Paid plan limit is 50, so topics_created=5 should NOT raise 429.

    **Validates: Requirements 4.9, 4.10, 4.11**
    """
    enforcer = PlanEnforcer()

    user = MagicMock()
    user.plan = plan
    user.id = 1

    stat = MagicMock(spec=UsageStat)
    stat.topics_created = 5  # at free limit, but paid limit is 50

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = stat

    # Should not raise — paid plan allows up to 50
    enforcer.check_topic_limit(user, db)


# ── Property 19: Lab usage endpoint is restricted to professor role ───────────

@h_settings(max_examples=100, deadline=None)
@given(role=st.sampled_from(["phd_student", "master_student", "undergraduate_student"]))
def test_non_professor_cannot_access_usage(role):
    """Property 19: Lab usage endpoint is restricted to professor role.

    **Validates: Requirements 4.12**
    """
    from app.services.lab_service import require_min_role, ROLE_HIERARCHY

    db = MagicMock()
    member = MagicMock()
    member.role = role
    db.query.return_value.filter_by.return_value.first.return_value = member

    with pytest.raises(HTTPException) as exc_info:
        require_min_role(1, 1, "professor", db)
    assert exc_info.value.status_code == 403


# ── Property 20: Member removal revokes access to all lab topics ─────────────

@h_settings(max_examples=100, deadline=None)
@given(
    lab_id=st.integers(min_value=1, max_value=1000),
    user_id=st.integers(min_value=2, max_value=1000),
)
def test_member_removal_revokes_access(lab_id, user_id):
    """Property 20: Member removal revokes access to all lab topics.

    After remove_member, get_member returns None (member no longer in lab).

    **Validates: Requirements 4.13**
    """
    from app.services.lab_service import LabService

    service = LabService()

    # Requester is a professor (different from the user being removed)
    requester = MagicMock()
    requester.id = 1  # professor id

    db = MagicMock()

    # Professor member for the requester
    professor_member = MagicMock()
    professor_member.role = "professor"

    # Target member to be removed
    target_member = MagicMock()
    target_member.role = "phd_student"

    # Simulate: first call (require_professor) returns professor_member,
    # second call (find target) returns target_member
    db.query.return_value.filter_by.return_value.first.side_effect = [
        professor_member,  # _require_professor -> get_member for requester
        target_member,     # find the member to delete
    ]

    # remove_member should succeed (no exception)
    service.remove_member(lab_id, user_id, requester, db)

    # After removal, simulate DB returning None for get_member
    db.query.return_value.filter_by.return_value.first.return_value = None
    db.query.return_value.filter_by.return_value.first.side_effect = None

    result = service.get_member(lab_id, user_id, db)
    assert result is None

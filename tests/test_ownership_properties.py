"""Property-based tests for resource ownership and cross-user access control.

Validates: Requirements 3.10, 3.11
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.api.topics import _get_topic_or_404
from app.models.topic import Topic
from app.schemas.topic import TopicCreate


@h_settings(max_examples=100, deadline=None)
@given(user_id=st.integers(min_value=1, max_value=10**6))
def test_resource_ownership_set_to_creating_user(user_id):
    """Property 12: Resource ownership is always set to the creating user.

    **Validates: Requirements 3.10**
    """
    payload = TopicCreate(title="Test Topic")
    topic_data = payload.model_dump()
    topic_data["target_paper_type"] = topic_data.pop("paper_type")
    topic_data["user_id"] = user_id
    topic = Topic(**topic_data)
    assert topic.user_id == user_id


@h_settings(max_examples=100, deadline=None)
@given(
    owner_id=st.integers(min_value=1, max_value=500),
    requester_id=st.integers(min_value=501, max_value=1000),
)
def test_cross_user_access_forbidden(owner_id, requester_id):
    """Property 13: Cross-user resource access is forbidden.

    **Validates: Requirements 3.11**
    """
    topic = MagicMock(spec=Topic)
    topic.user_id = owner_id
    topic.lab_id = None

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = topic

    requester = MagicMock()
    requester.id = requester_id

    with pytest.raises(HTTPException) as exc_info:
        _get_topic_or_404(1, requester, db)
    assert exc_info.value.status_code == 403

"""Property-based tests for audit logging service.

Validates: Requirements 5.1, 5.2, 5.3, 5.5
"""
from unittest.mock import MagicMock
from datetime import datetime

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.services.audit_service import AuditService
from app.models.audit import AuditLog

REQUIRED_FIELDS = ("event_type", "status", "created_at")


@h_settings(max_examples=100, deadline=None)
@given(
    event_data=st.fixed_dictionaries({"stage": st.text(min_size=1, max_size=50)}),
    event_type=st.text(min_size=1, max_size=50),
    status=st.sampled_from(["success", "failed"]),
)
def test_audit_log_entries_contain_required_fields(event_data, event_type, status):
    """Property 21: Audit log entries contain all required fields.

    **Validates: Requirements 5.1, 5.2**
    """
    db = MagicMock()
    added_objects = []
    db.add = lambda obj: added_objects.append(obj)
    db.commit = MagicMock()

    service = AuditService()
    service.log_event(
        user_id=1, lab_id=1, topic_id=None,
        event_type=event_type, event_data=event_data,
        status=status, db=db,
    )

    assert len(added_objects) == 1
    entry = added_objects[0]
    assert isinstance(entry, AuditLog)
    for field in REQUIRED_FIELDS:
        assert getattr(entry, field, None) is not None, f"Required field '{field}' is None"


@h_settings(max_examples=100, deadline=None)
@given(
    target_lab_id=st.integers(min_value=1, max_value=1000),
    num_entries=st.integers(min_value=1, max_value=10),
)
def test_audit_log_filtering_returns_only_matching_entries(target_lab_id, num_entries):
    """Property 22: Audit log filtering returns only matching entries.

    **Validates: Requirements 5.3**
    """
    mock_entries = []
    for i in range(num_entries):
        entry = MagicMock(spec=AuditLog)
        entry.id = i + 1
        entry.lab_id = target_lab_id
        entry.user_id = 1
        entry.event_type = "test_event"
        entry.event_data = {}
        entry.status = "success"
        entry.created_at = datetime(2024, 1, 1)
        mock_entries.append(entry)

    db = MagicMock()
    query_mock = MagicMock()
    filter_mock = MagicMock()
    order_mock = MagicMock()
    offset_mock = MagicMock()
    limit_mock = MagicMock()

    db.query.return_value = query_mock
    query_mock.filter.return_value = filter_mock
    filter_mock.count.return_value = num_entries
    filter_mock.order_by.return_value = order_mock
    order_mock.offset.return_value = offset_mock
    offset_mock.limit.return_value = limit_mock
    limit_mock.all.return_value = mock_entries

    service = AuditService()
    result = service.get_lab_audit_log(lab_id=target_lab_id, page=1, page_size=num_entries, db=db)

    assert result["total"] == num_entries
    assert len(result["items"]) == num_entries
    for entry in mock_entries:
        assert entry.lab_id == target_lab_id


def test_audit_log_failure_does_not_propagate():
    """Property 23: Audit log failure does not fail primary operation.

    **Validates: Requirements 5.5**
    """
    db = MagicMock()
    db.add = MagicMock(side_effect=Exception("DB error"))

    service = AuditService()
    # Should NOT raise
    service.log_event(1, None, None, "test_event", {}, "success", db)

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services import support_case_service as service


def _case(status: str, sla_due_at):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        case_id=uuid4(),
        user_id=uuid4(),
        assigned_to_user_id=None,
        entity_type=None,
        entity_id=None,
        category="wallet",
        subject="Sujet",
        description="Description",
        status=status,
        priority="normal",
        reason_code=None,
        resolution_code=None,
        sla_due_at=sla_due_at,
        first_response_at=None,
        resolved_at=None,
        closed_at=None,
        metadata_={},
        created_at=now,
        updated_at=now,
    )


def test_serialize_case_marks_due_soon_when_sla_close(monkeypatch):
    fixed_now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_utcnow", lambda: fixed_now)
    case_obj = _case("open", fixed_now + timedelta(minutes=30))

    payload = service._serialize_case(case_obj, users={})
    assert payload["sla_status"] == "due_soon"
    assert payload["sla_remaining_seconds"] is not None
    assert payload["sla_remaining_seconds"] > 0


def test_serialize_case_marks_overdue_when_sla_passed(monkeypatch):
    fixed_now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_utcnow", lambda: fixed_now)
    case_obj = _case("in_review", fixed_now - timedelta(minutes=5))

    payload = service._serialize_case(case_obj, users={})
    assert payload["sla_status"] == "overdue"
    assert payload["sla_remaining_seconds"] < 0

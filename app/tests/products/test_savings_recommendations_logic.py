from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.savings_service import _serialize_goal


def test_serialize_goal_exposes_recommended_contributions_when_target_date_is_future():
    now = datetime.now(timezone.utc)
    goal = SimpleNamespace(
        goal_id=uuid4(),
        user_id=uuid4(),
        title="Projet",
        note=None,
        currency_code="EUR",
        target_amount=Decimal("1000"),
        current_amount=Decimal("200"),
        locked=False,
        target_date=now + timedelta(days=40),
        status="active",
        metadata_={},
        created_at=now,
        updated_at=now,
    )

    payload = _serialize_goal(goal, movements=[])
    assert payload["remaining_amount"] == Decimal("800")
    assert payload["recommended_weekly_amount"] is not None
    assert payload["recommended_monthly_amount"] is not None


def test_serialize_goal_recommendations_none_without_target_date():
    now = datetime.now(timezone.utc)
    goal = SimpleNamespace(
        goal_id=uuid4(),
        user_id=uuid4(),
        title="Projet",
        note=None,
        currency_code="EUR",
        target_amount=Decimal("1000"),
        current_amount=Decimal("200"),
        locked=False,
        target_date=None,
        status="active",
        metadata_={},
        created_at=now,
        updated_at=now,
    )

    payload = _serialize_goal(goal, movements=[])
    assert payload["recommended_weekly_amount"] is None
    assert payload["recommended_monthly_amount"] is None

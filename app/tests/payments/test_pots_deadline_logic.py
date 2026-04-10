from datetime import datetime, timedelta, timezone

from app.services.pots_service import _pot_deadline_metrics


def test_pot_deadline_metrics_for_future_deadline():
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    days_remaining, deadline_passed = _pot_deadline_metrics(
        deadline_at=now + timedelta(days=3, hours=2),
        now=now,
    )
    assert deadline_passed is False
    assert days_remaining == 4


def test_pot_deadline_metrics_for_past_deadline():
    now = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    days_remaining, deadline_passed = _pot_deadline_metrics(
        deadline_at=now - timedelta(minutes=1),
        now=now,
    )
    assert deadline_passed is True
    assert days_remaining == 0

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import asyncio

from app.models.payment_requests import PaymentRequests
from fastapi import HTTPException

from app.schemas.payment_requests import PaymentRequestCreate
from app.services.payment_request_service import (
    _build_recurrence_config,
    _compute_next_due_at,
    _compute_next_expires_at,
    _extract_reminder_fields,
    _set_manual_reminder_metadata,
)
from app.services import payment_request_service as service


def test_compute_next_due_daily_and_weekly():
    base = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    assert _compute_next_due_at(base, frequency="daily") == base + timedelta(days=1)
    assert _compute_next_due_at(base, frequency="weekly") == base + timedelta(days=7)


def test_compute_next_due_monthly_handles_end_of_month():
    base = datetime(2026, 1, 31, 10, 0, tzinfo=timezone.utc)
    result = _compute_next_due_at(base, frequency="monthly")
    assert result == datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc)


def test_compute_next_expires_preserves_positive_delta():
    current_due = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    current_expires = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    next_due = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    assert _compute_next_expires_at(
        current_due_at=current_due,
        current_expires_at=current_expires,
        next_due_at=next_due,
    ) == datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc)


def test_compute_next_expires_returns_none_for_non_positive_delta():
    current_due = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    current_expires = datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc)
    next_due = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    assert (
        _compute_next_expires_at(
            current_due_at=current_due,
            current_expires_at=current_expires,
            next_due_at=next_due,
        )
        is None
    )


class _CreateNextRecurringDb:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if isinstance(item, PaymentRequests) and not getattr(item, "request_id", None):
                item.request_id = uuid4()


def test_create_next_recurring_payment_request_creates_followup(monkeypatch):
    requester_id = uuid4()
    payer_id = uuid4()
    requester_wallet_id = uuid4()
    payer_wallet_id = uuid4()
    source_request_id = uuid4()
    fixed_now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    due_at = datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)
    expires_at = datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc)
    db = _CreateNextRecurringDb()
    event_types = []
    notified = []

    async def fake_get_user_wallet(*args, **kwargs):
        return None

    async def fake_append_event(*args, **kwargs):
        event_types.append(kwargs["event_type"])

    async def fake_send_notification(user_id, message):
        notified.append((user_id, message))

    monkeypatch.setattr(service, "_utcnow", lambda: fixed_now)
    monkeypatch.setattr(service, "_get_user_wallet", fake_get_user_wallet)
    monkeypatch.setattr(service, "_append_event", fake_append_event)
    monkeypatch.setattr(service, "send_notification", fake_send_notification)

    source_request = PaymentRequests(
        request_id=source_request_id,
        requester_user_id=requester_id,
        payer_user_id=payer_id,
        requester_wallet_id=requester_wallet_id,
        payer_wallet_id=payer_wallet_id,
        amount=Decimal("80.00"),
        currency_code="EUR",
        status="paid",
        channel="direct",
        title="Abonnement",
        note="Mensuel",
        due_at=due_at,
        expires_at=expires_at,
        metadata_={
            "recurrence": {"frequency": "weekly", "count": 4, "end_at": None},
            "auto_pay": {"enabled": True, "max_amount": "100.00"},
        },
        created_at=fixed_now,
        updated_at=fixed_now,
    )

    next_request = asyncio.run(
        service._create_next_recurring_payment_request_if_needed(
            db,
            source_request=source_request,
        )
    )

    assert next_request is not None
    assert next_request.requester_user_id == requester_id
    assert next_request.payer_user_id == payer_id
    assert next_request.requester_wallet_id == requester_wallet_id
    assert next_request.payer_wallet_id == payer_wallet_id
    assert next_request.status == "pending"
    assert next_request.due_at == due_at + timedelta(days=7)
    assert next_request.expires_at == expires_at + timedelta(days=7)
    assert next_request.metadata_["recurrence"]["count"] == 3
    assert next_request.metadata_["recurrence_root_request_id"] == str(source_request_id)
    assert next_request.metadata_["recurrence_previous_request_id"] == str(source_request_id)
    assert next_request.metadata_["reminder"]["manual_count"] == 0
    assert next_request.metadata_["reminder"]["next_manual_at"] is None
    assert event_types == ["created", "sent"]
    assert len(notified) == 1
    assert notified[0][0] == str(payer_id)


def test_create_next_recurring_payment_request_stops_when_count_is_last(monkeypatch):
    source_request = PaymentRequests(
        request_id=uuid4(),
        requester_user_id=uuid4(),
        payer_user_id=uuid4(),
        requester_wallet_id=uuid4(),
        payer_wallet_id=uuid4(),
        amount=Decimal("25.00"),
        currency_code="EUR",
        status="paid",
        channel="direct",
        due_at=datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
        metadata_={"recurrence": {"frequency": "daily", "count": 1, "end_at": None}},
    )

    next_request = asyncio.run(
        service._create_next_recurring_payment_request_if_needed(
            _CreateNextRecurringDb(),
            source_request=source_request,
        )
    )

    assert next_request is None


def test_create_next_recurring_payment_request_stops_after_end_at(monkeypatch):
    source_request = PaymentRequests(
        request_id=uuid4(),
        requester_user_id=uuid4(),
        payer_user_id=uuid4(),
        requester_wallet_id=uuid4(),
        payer_wallet_id=uuid4(),
        amount=Decimal("25.00"),
        currency_code="EUR",
        status="paid",
        channel="direct",
        due_at=datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
        metadata_={"recurrence": {"frequency": "monthly", "count": None, "end_at": "2026-05-09T09:00:00+00:00"}},
    )

    next_request = asyncio.run(
        service._create_next_recurring_payment_request_if_needed(
            _CreateNextRecurringDb(),
            source_request=source_request,
        )
    )

    assert next_request is None


def test_build_recurrence_config_rejects_autopay_enabled_on_create():
    payload = PaymentRequestCreate(
        payer_identifier="@bob",
        amount=Decimal("50"),
        currency_code="EUR",
        due_at=datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
        recurrence_frequency="weekly",
        auto_pay_enabled=True,
    )

    try:
        _build_recurrence_config(payload, amount=Decimal("50"))
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Auto-pay doit etre activee par le payeur" in str(exc.detail)


def test_build_recurrence_config_rejects_autopay_limit_on_create():
    payload = PaymentRequestCreate(
        payer_identifier="@bob",
        amount=Decimal("50"),
        currency_code="EUR",
        due_at=datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
        recurrence_frequency="weekly",
        auto_pay_max_amount=Decimal("60"),
    )

    try:
        _build_recurrence_config(payload, amount=Decimal("50"))
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Auto-pay doit etre activee par le payeur" in str(exc.detail)


def test_build_recurrence_config_initializes_reminder_guardrails():
    payload = PaymentRequestCreate(
        payer_identifier="@bob",
        amount=Decimal("50"),
        currency_code="EUR",
        due_at=datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
        recurrence_frequency="weekly",
    )

    config = _build_recurrence_config(payload, amount=Decimal("50"))
    assert config["reminder"]["manual_count"] == 0
    assert config["reminder"]["next_manual_at"] is None


def test_manual_reminder_metadata_sets_cooldown_and_counter():
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    metadata = _set_manual_reminder_metadata({"reminder": {"manual_count": 2}}, now=now)
    fields = _extract_reminder_fields(metadata, now=now)
    assert fields["manual_reminder_count"] == 3
    assert fields["can_send_manual_reminder"] is False

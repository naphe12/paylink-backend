import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.scheduled_transfers import ScheduledTransferCreate
from app.services import scheduled_transfer_service as service
from fastapi import HTTPException


class _CreateDb:
    def __init__(self):
        self.added = []
        self.wallet = SimpleNamespace(wallet_id=uuid4(), currency_code="EUR")

    async def scalar(self, _stmt):
        return self.wallet

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        return None

    async def refresh(self, item):
        now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
        if not getattr(item, "schedule_id", None):
            item.schedule_id = uuid4()
        if not getattr(item, "created_at", None):
            item.created_at = now
        item.updated_at = now


class _RunDb:
    async def commit(self):
        return None

    async def refresh(self, _item):
        return None


class _ScalarSequenceDb:
    def __init__(self, values):
        self.values = iter(values)
        self.statements = []

    async def scalar(self, stmt):
        self.statements.append(stmt)
        return next(self.values)

    def add(self, _item):
        return None

    async def flush(self):
        return None


class _UpdateDb:
    def __init__(self, item):
        self.item = item

    async def scalar(self, _stmt):
        return self.item

    async def commit(self):
        return None

    async def refresh(self, _item):
        return None


class _FakeScheduledTransfer:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.schedule_id = None
        self.created_at = None
        self.updated_at = None
        self.last_run_at = None
        self.last_result = None


def test_normalize_internal_receiver_accepts_paytag_without_at_and_extra_spaces():
    assert service._normalize_receiver_identifier("  Alice  ") == ("Alice", "alice", "@alice")


def test_resolve_internal_receiver_supports_username_paytag_email_and_phone():
    receiver = SimpleNamespace(user_id=uuid4())
    db = _ScalarSequenceDb([receiver])

    result = asyncio.run(service._resolve_receiver(db, " Alice "))

    assert result is receiver
    sql = str(db.statements[0])
    assert "lower(paylink.users.email)" in sql
    assert "lower(paylink.users.username)" in sql
    assert "lower(paylink.users.paytag)" in sql
    assert "paylink.users.phone_e164" in sql


def test_create_internal_schedule_rejects_self_transfer():
    user_id = uuid4()
    current_user = SimpleNamespace(
        user_id=user_id,
        email="alice@example.com",
        username="alice",
        paytag="@alice",
        phone_e164="+25761234567",
    )
    sender_wallet = SimpleNamespace(wallet_id=uuid4(), currency_code="EUR")
    db = _ScalarSequenceDb([sender_wallet, current_user])
    payload = ScheduledTransferCreate(
        transfer_type="internal",
        receiver_identifier="alice",
        amount=Decimal("10.00"),
        frequency="weekly",
        next_run_at=datetime(2027, 4, 8, 8, 0, tzinfo=timezone.utc),
    )

    try:
        asyncio.run(service.create_scheduled_transfer(db, current_user=current_user, payload=payload))
        assert False, "Expected self-transfer validation error"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "vous-meme" in str(exc.detail)


def test_execute_internal_schedule_uses_credit_with_negative_wallet(monkeypatch):
    sender = SimpleNamespace(
        user_id=uuid4(), email="sender@example.com", paytag="@sender",
        credit_limit=Decimal("100"), credit_used=Decimal("20"),
    )
    receiver = SimpleNamespace(user_id=uuid4(), email="receiver@example.com", paytag="@receiver")
    sender_wallet = SimpleNamespace(wallet_id=uuid4(), user_id=sender.user_id, available=Decimal("-10"), currency_code="EUR")
    receiver_wallet = SimpleNamespace(wallet_id=uuid4(), user_id=receiver.user_id, available=Decimal("5"), currency_code="EUR")
    credit_line = SimpleNamespace(
        initial_amount=Decimal("100"), used_amount=Decimal("20"), outstanding_amount=Decimal("80"),
        currency_code="EUR", updated_at=None,
    )
    db = _ScalarSequenceDb([receiver, sender_wallet, receiver_wallet, credit_line])

    async def fake_movement(*args, **kwargs):
        return None

    class FakeTransaction:
        def __init__(self, **kwargs):
            self.tx_id = uuid4()

    class FakeLedger:
        def __init__(self, _db): pass
        async def ensure_wallet_account(self, wallet): return wallet.wallet_id
        async def post_journal(self, **kwargs): return None

    monkeypatch.setattr(service, "log_wallet_movement", fake_movement)
    monkeypatch.setattr(service, "Transactions", FakeTransaction)
    monkeypatch.setattr(service, "LedgerService", FakeLedger)

    result = asyncio.run(service._execute_internal_transfer(
        db, sender=sender, receiver_identifier="receiver", amount=Decimal("50"), schedule_id=uuid4()
    ))

    assert sender_wallet.available == Decimal("-60")
    assert receiver_wallet.available == Decimal("55")
    assert credit_line.used_amount == Decimal("70")
    assert credit_line.outstanding_amount == Decimal("30")
    assert result["credit_used"] == Decimal("50")


def test_create_scheduled_transfer_supports_external_payload(monkeypatch):
    db = _CreateDb()
    current_user = SimpleNamespace(user_id=uuid4())
    payload = ScheduledTransferCreate(
        transfer_type="external",
        amount=Decimal("125.00"),
        frequency="monthly",
        next_run_at=datetime(2027, 4, 8, 8, 0, tzinfo=timezone.utc),
        note="Famille",
        external_transfer={
            "partner_name": "Lumicash",
            "country_destination": "Burundi",
            "recipient_name": "Jean Ndayishimiye",
            "recipient_phone": "+25761234567",
            "recipient_email": "jean@example.com",
        },
    )

    monkeypatch.setattr(service, "ScheduledTransfers", _FakeScheduledTransfer)

    result = asyncio.run(service.create_scheduled_transfer(db, current_user=current_user, payload=payload))

    assert result["transfer_type"] == "external"
    assert result["receiver_identifier"] == "+25761234567"
    assert result["external_transfer"]["partner_name"] == "Lumicash"
    assert db.added[0].metadata_["transfer_type"] == "external"
    assert db.added[0].metadata_["external_transfer"]["country_destination"] == "Burundi"
    assert db.added[0].metadata_["monthly_anchor_day"] == 8
    assert db.added[0].metadata_["max_consecutive_failures"] == 3
    assert db.added[0].metadata_["failure_count"] == 0


def test_run_scheduled_transfer_item_executes_external_schedule(monkeypatch, caplog):
    schedule_id = uuid4()
    current_user = SimpleNamespace(user_id=uuid4(), email="client@example.com", paytag="@client")
    next_run_at = datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc)
    execution_time = datetime(2026, 4, 8, 8, 5, tzinfo=timezone.utc)
    item = SimpleNamespace(
        schedule_id=schedule_id,
        user_id=current_user.user_id,
        receiver_user_id=None,
        receiver_identifier="+25761234567",
        amount=Decimal("125.00"),
        currency_code="EUR",
        frequency="weekly",
        status="active",
        note="Famille",
        next_run_at=next_run_at,
        last_run_at=None,
        last_result=None,
        remaining_runs=2,
        metadata_={
            "transfer_type": "external",
            "external_transfer": {
                "partner_name": "Lumicash",
                "country_destination": "Burundi",
                "recipient_name": "Jean Ndayishimiye",
                "recipient_phone": "+25761234567",
            },
        },
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
    )

    async def fake_execute_external_transfer(db, *, sender, item):
        assert sender.user_id == current_user.user_id
        assert item.schedule_id == schedule_id
        return {
            "transfer_id": str(uuid4()),
            "reference_code": "EXT-ABCD1234",
            "status": "approved",
            "currency": "EUR",
        }

    monkeypatch.setattr(service, "_execute_external_transfer", fake_execute_external_transfer)
    monkeypatch.setattr(service, "_utcnow", lambda: execution_time)

    with caplog.at_level(logging.INFO, logger=service.__name__):
        result = asyncio.run(
            service._run_scheduled_transfer_item(
                _RunDb(),
                current_user=current_user,
                item=item,
                raise_on_failure=True,
            )
        )

    assert result["status"] == "active"
    assert result["transfer_type"] == "external"
    assert result["last_result"] == "Transfert externe planifie: approved (EXT-ABCD1234)"
    assert result["external_transfer"]["recipient_name"] == "Jean Ndayishimiye"
    assert item.last_run_at == execution_time
    assert item.next_run_at == next_run_at + timedelta(days=7)
    assert item.remaining_runs == 1
    assert "Scheduled transfer succeeded" in caplog.text
    assert str(schedule_id) in caplog.text
    assert "transfer_type=external" in caplog.text


def test_execute_external_transfer_enables_inline_notifications(monkeypatch):
    sender = SimpleNamespace(user_id=uuid4(), email="client@example.com", paytag="@client")
    item = SimpleNamespace(
        amount=Decimal("10.00"),
        metadata_={
            "transfer_type": "external",
            "external_transfer": {
                "partner_name": "Lumicash",
                "country_destination": "Burundi",
                "recipient_name": "Jean",
                "recipient_phone": "+25761234567",
                "recipient_email": "jean@example.com",
            },
        },
    )
    inline_notifications = {"value": False}

    async def fake_core(
        *,
        data,
        background_tasks,
        idempotency_key,
        db,
        current_user,
        execute_notifications_inline=False,
    ):
        assert str(data.recipient_email) == "jean@example.com"
        assert current_user.user_id == sender.user_id
        assert execute_notifications_inline is True
        inline_notifications["value"] = True
        return {"status": "approved", "reference_code": "EXT-TEST1234", "currency": "EUR"}

    from app.routers.wallet import transfer as transfer_module

    monkeypatch.setattr(transfer_module, "_external_transfer_core", fake_core)

    result = asyncio.run(service._execute_external_transfer(_RunDb(), sender=sender, item=item))

    assert result["status"] == "approved"
    assert inline_notifications["value"] is True


def test_advance_next_run_monthly_preserves_calendar_month():
    january_end = datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc)
    february = service._advance_next_run(january_end, "monthly")
    march = service._advance_next_run(february, "monthly")

    assert february == datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc)
    assert march == datetime(2026, 3, 28, 8, 0, tzinfo=timezone.utc)


def test_advance_next_run_monthly_with_anchor_restores_end_of_month():
    january_end = datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc)
    february = service._advance_next_run(january_end, "monthly", monthly_anchor_day=31)
    march = service._advance_next_run(february, "monthly", monthly_anchor_day=31)

    assert february == datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc)
    assert march == datetime(2026, 3, 31, 8, 0, tzinfo=timezone.utc)


def test_run_scheduled_transfer_item_backfills_monthly_anchor_from_last_run(monkeypatch):
    current_user = SimpleNamespace(user_id=uuid4(), email="client@example.com", paytag="@client")
    execution_time = datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc)
    item = SimpleNamespace(
        schedule_id=uuid4(),
        user_id=current_user.user_id,
        receiver_user_id=uuid4(),
        receiver_identifier="@alice",
        amount=Decimal("42.00"),
        currency_code="EUR",
        frequency="monthly",
        status="active",
        note="Loyer",
        next_run_at=datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc),
        last_run_at=datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc),
        last_result=None,
        remaining_runs=None,
        metadata_={"transfer_type": "internal"},
        created_at=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
    )

    async def fake_execute_internal_transfer(db, *, sender, receiver_identifier, amount, note, schedule_id):
        assert sender.user_id == current_user.user_id
        assert receiver_identifier == "@alice"
        assert amount == Decimal("42.00")
        return {
            "receiver_user_id": item.receiver_user_id,
            "currency_code": "EUR",
            "tx_id": uuid4(),
        }

    monkeypatch.setattr(service, "_execute_internal_transfer", fake_execute_internal_transfer)
    monkeypatch.setattr(service, "_utcnow", lambda: execution_time)

    result = asyncio.run(
        service._run_scheduled_transfer_item(
            _RunDb(),
            current_user=current_user,
            item=item,
            raise_on_failure=True,
        )
    )

    assert result["status"] == "active"
    assert item.metadata_["monthly_anchor_day"] == 31
    assert item.next_run_at == datetime(2026, 3, 31, 8, 0, tzinfo=timezone.utc)


def test_run_scheduled_transfer_item_auto_pauses_after_max_failures(monkeypatch, caplog):
    current_user = SimpleNamespace(user_id=uuid4(), email="client@example.com", paytag="@client")
    item = SimpleNamespace(
        schedule_id=uuid4(),
        user_id=current_user.user_id,
        receiver_user_id=uuid4(),
        receiver_identifier="@alice",
        amount=Decimal("15.00"),
        currency_code="EUR",
        frequency="weekly",
        status="active",
        note="Test",
        next_run_at=datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc),
        last_run_at=None,
        last_result=None,
        remaining_runs=None,
        metadata_={"transfer_type": "internal", "failure_count": 2, "max_consecutive_failures": 3},
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
    )

    async def fake_execute_internal_transfer(*args, **kwargs):
        raise HTTPException(status_code=400, detail="Solde insuffisant")

    monkeypatch.setattr(service, "_execute_internal_transfer", fake_execute_internal_transfer)

    with caplog.at_level(logging.WARNING, logger=service.__name__):
        result = asyncio.run(
            service._run_scheduled_transfer_item(
                _RunDb(),
                current_user=current_user,
                item=item,
                raise_on_failure=False,
            )
        )

    assert result["status"] == "paused"
    assert result["failure_count"] == 3
    assert result["auto_paused_for_failures"] is True
    assert "Mise en pause auto" in (result["last_result"] or "")
    assert "Scheduled transfer failed" in caplog.text
    assert str(item.schedule_id) in caplog.text
    assert "reason=Solde insuffisant" in caplog.text


def test_run_scheduled_transfer_item_handles_unexpected_exception(monkeypatch):
    current_user = SimpleNamespace(user_id=uuid4(), email="client@example.com", paytag="@client")
    item = SimpleNamespace(
        schedule_id=uuid4(),
        user_id=current_user.user_id,
        receiver_user_id=None,
        receiver_identifier="+25761234567",
        amount=Decimal("12.00"),
        currency_code="EUR",
        frequency="weekly",
        status="active",
        note="Test",
        next_run_at=datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc),
        last_run_at=None,
        last_result=None,
        remaining_runs=None,
        metadata_={
            "transfer_type": "external",
            "external_transfer": {
                "partner_name": "Lumicash",
                "country_destination": "Burundi",
                "recipient_name": "Jean",
                "recipient_phone": "+25761234567",
            },
            "failure_count": 0,
            "max_consecutive_failures": 3,
        },
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
    )

    async def fake_execute_external_transfer(*args, **kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(service, "_execute_external_transfer", fake_execute_external_transfer)

    result = asyncio.run(
        service._run_scheduled_transfer_item(
            _RunDb(),
            current_user=current_user,
            item=item,
            raise_on_failure=False,
        )
    )

    assert result["status"] == "failed"
    assert result["failure_count"] == 1
    assert "Erreur technique planification" in (result["last_result"] or "")


def test_run_scheduled_transfer_item_surfaces_value_error_message(monkeypatch):
    current_user = SimpleNamespace(user_id=uuid4(), email="client@example.com", paytag="@client")
    item = SimpleNamespace(
        schedule_id=uuid4(),
        user_id=current_user.user_id,
        receiver_user_id=None,
        receiver_identifier="+25761234567",
        amount=Decimal("12.00"),
        currency_code="EUR",
        frequency="weekly",
        status="active",
        note="Test",
        next_run_at=datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc),
        last_run_at=None,
        last_result=None,
        remaining_runs=None,
        metadata_={
            "transfer_type": "external",
            "external_transfer": {
                "partner_name": "Lumicash",
                "country_destination": "Burundi",
                "recipient_name": "Jean",
                "recipient_phone": "+25761234567",
            },
            "failure_count": 0,
            "max_consecutive_failures": 3,
        },
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
    )

    async def fake_execute_external_transfer(*args, **kwargs):
        raise ValueError("Devise incoherente entre lignes comptables")

    monkeypatch.setattr(service, "_execute_external_transfer", fake_execute_external_transfer)

    result = asyncio.run(
        service._run_scheduled_transfer_item(
            _RunDb(),
            current_user=current_user,
            item=item,
            raise_on_failure=False,
        )
    )

    assert result["status"] == "failed"
    assert result["failure_count"] == 1
    assert result["last_result"] == "Devise incoherente entre lignes comptables"


def test_update_scheduled_transfer_updates_programming(monkeypatch):
    current_user = SimpleNamespace(user_id=uuid4())
    schedule_id = uuid4()
    item = SimpleNamespace(
        schedule_id=schedule_id,
        user_id=current_user.user_id,
        receiver_user_id=uuid4(),
        receiver_identifier="@alice",
        amount=Decimal("20.00"),
        currency_code="EUR",
        frequency="weekly",
        status="active",
        note="Old note",
        next_run_at=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
        last_run_at=None,
        last_result=None,
        remaining_runs=4,
        metadata_={"transfer_type": "internal", "failure_count": 2, "max_consecutive_failures": 3},
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
    )
    db = _UpdateDb(item)
    now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_utcnow", lambda: now)

    payload = SimpleNamespace(
        model_dump=lambda **kwargs: {
            "frequency": "monthly",
            "next_run_at": datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
            "remaining_runs": 2,
            "max_consecutive_failures": 5,
            "note": "Nouveau planning",
        }
    )

    result = asyncio.run(
        service.update_scheduled_transfer(
            db,
            current_user=current_user,
            schedule_id=schedule_id,
            payload=payload,
        )
    )

    assert result["frequency"] == "monthly"
    assert result["remaining_runs"] == 2
    assert result["max_consecutive_failures"] == 5
    assert result["note"] == "Nouveau planning"
    assert result["last_result"] == "Programmation modifiee par l'utilisateur"
    assert item.metadata_["failure_count"] == 0
    assert item.metadata_["monthly_anchor_day"] == 15

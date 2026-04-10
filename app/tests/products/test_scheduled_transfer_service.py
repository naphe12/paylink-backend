import asyncio
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


def test_run_scheduled_transfer_item_executes_external_schedule(monkeypatch):
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


def test_execute_external_transfer_runs_background_tasks(monkeypatch):
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
    task_executed = {"value": False}

    async def fake_core(*, data, background_tasks, idempotency_key, db, current_user):
        assert str(data.recipient_email) == "jean@example.com"
        assert current_user.user_id == sender.user_id

        async def fake_task():
            task_executed["value"] = True

        background_tasks.add_task(fake_task)
        return {"status": "approved", "reference_code": "EXT-TEST1234", "currency": "EUR"}

    from app.routers.wallet import transfer as transfer_module

    monkeypatch.setattr(transfer_module, "_external_transfer_core", fake_core)

    result = asyncio.run(service._execute_external_transfer(_RunDb(), sender=sender, item=item))

    assert result["status"] == "approved"
    assert task_executed["value"] is True


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


def test_run_scheduled_transfer_item_auto_pauses_after_max_failures(monkeypatch):
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

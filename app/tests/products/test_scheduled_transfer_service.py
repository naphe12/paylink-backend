import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.scheduled_transfers import ScheduledTransferCreate
from app.services import scheduled_transfer_service as service


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
        next_run_at=datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc),
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

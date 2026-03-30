import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.models.escrow_enums import EscrowOrderStatus
from app.services import escrow_service as escrow_service_module


class _FakeDb:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


def test_escrow_service_canonical_status_flow(monkeypatch):
    events = []

    async def _fake_credit_user_usdc(user_id, amount, db, ref, description):
        events.append(("credit", user_id, amount, ref, description))

    async def _fake_broadcast(order):
        events.append(("broadcast", order.status.value))

    monkeypatch.setattr(escrow_service_module, "credit_user_usdc", _fake_credit_user_usdc)
    monkeypatch.setattr(escrow_service_module, "broadcast_tracking_update", _fake_broadcast)

    db = _FakeDb()
    order = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=EscrowOrderStatus.CREATED,
        usdc_expected=Decimal("100"),
        usdc_received=Decimal("100"),
        funded_at=None,
        swapped_at=None,
        payout_initiated_at=None,
        paid_out_at=None,
    )

    asyncio.run(escrow_service_module.EscrowService.mark_funded(db, order))
    assert order.status == EscrowOrderStatus.FUNDED
    assert order.funded_at is not None

    asyncio.run(escrow_service_module.EscrowService.mark_swapped(db, order))
    assert order.status == EscrowOrderStatus.SWAPPED
    assert order.swapped_at is not None

    asyncio.run(escrow_service_module.EscrowService.mark_payout_pending(db, order))
    assert order.status == EscrowOrderStatus.PAYOUT_PENDING
    assert order.payout_initiated_at is not None

    asyncio.run(escrow_service_module.EscrowService.mark_paid_out(db, order))
    assert order.status == EscrowOrderStatus.PAID_OUT
    assert order.paid_out_at is not None

    credit_events = [event for event in events if event[0] == "credit"]
    broadcast_events = [event for event in events if event[0] == "broadcast"]

    assert len(credit_events) == 1
    assert credit_events[0][1] == str(order.user_id)
    assert credit_events[0][2] == Decimal("100")
    assert len(broadcast_events) == 4
    assert [event[1] for event in broadcast_events] == [
        "FUNDED",
        "SWAPPED",
        "PAYOUT_PENDING",
        "PAID_OUT",
    ]
    assert db.commits == 4

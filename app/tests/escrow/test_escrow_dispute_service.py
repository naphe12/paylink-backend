import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.models.escrow_enums import EscrowOrderStatus
from app.services import escrow_dispute_service as escrow_dispute_service_module


class _FakeDb:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def test_request_escrow_refund(monkeypatch):
    events = []
    db = _FakeDb()
    order = SimpleNamespace(
        id=uuid4(),
        status=EscrowOrderStatus.SWAPPED,
        updated_at=None,
    )

    async def _fake_audit(db_arg, **kwargs):
        events.append(("audit", kwargs["action"], kwargs["metadata"]["after"]["status"]))

    async def _fake_broadcast(order_obj):
        events.append(("broadcast", order_obj.status.value))

    monkeypatch.setattr(escrow_dispute_service_module, "audit", _fake_audit)
    monkeypatch.setattr(escrow_dispute_service_module, "broadcast_tracking_update", _fake_broadcast)

    refunded = asyncio.run(
        escrow_dispute_service_module.EscrowDisputeService.request_refund(
            db,
            order,
            actor_user_id=str(uuid4()),
            actor_role="ADMIN",
            reason="Payout failed",
            reason_code="payout_failed",
            proof_type="mobile_money_reference",
            proof_ref="MM-REF-1",
        )
    )

    assert refunded.status == EscrowOrderStatus.REFUND_PENDING
    assert refunded.updated_at is not None
    assert db.commits == 1
    assert events == [
        ("audit", "ESCROW_REFUND_REQUESTED", "REFUND_PENDING"),
        ("broadcast", "REFUND_PENDING"),
    ]


def test_confirm_escrow_refund(monkeypatch):
    events = []
    db = _FakeDb()
    order = SimpleNamespace(
        id=uuid4(),
        status=EscrowOrderStatus.REFUND_PENDING,
        updated_at=None,
    )

    async def _fake_audit(db_arg, **kwargs):
        events.append(("audit", kwargs["action"], kwargs["metadata"]["after"]["status"]))

    async def _fake_broadcast(order_obj):
        events.append(("broadcast", order_obj.status.value))

    monkeypatch.setattr(escrow_dispute_service_module, "audit", _fake_audit)
    monkeypatch.setattr(escrow_dispute_service_module, "broadcast_tracking_update", _fake_broadcast)

    refunded = asyncio.run(
        escrow_dispute_service_module.EscrowDisputeService.confirm_refund(
            db,
            order,
            actor_user_id=str(uuid4()),
            actor_role="ADMIN",
            resolution="Refund approved after payout issue",
            resolution_code="refund_approved",
            proof_type="receipt_id",
            proof_ref="RCPT-9",
        )
    )

    assert refunded.status == EscrowOrderStatus.REFUNDED
    assert refunded.updated_at is not None
    assert db.commits == 1
    assert events == [
        ("audit", "ESCROW_REFUNDED", "REFUNDED"),
        ("broadcast", "REFUNDED"),
    ]

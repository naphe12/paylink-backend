import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.p2p_enums import DisputeStatus, TradeStatus
from app.services import p2p_dispute_service as p2p_dispute_service_module


class _FakeDb:
    def __init__(self, scalar_values):
        self._scalar_values = list(scalar_values)
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def scalar(self, stmt):
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        return obj


class _FakeDispute:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.dispute_id = kwargs.get("dispute_id", uuid4())


class _DummySelect:
    def where(self, *args, **kwargs):
        return self


def test_open_p2p_dispute_by_party_sets_trade_disputed(monkeypatch):
    trade = SimpleNamespace(
        trade_id=uuid4(),
        buyer_id=uuid4(),
        seller_id=uuid4(),
        status=TradeStatus.FIAT_SENT,
    )
    db = _FakeDb([trade])
    state_events = []
    audit_events = []

    async def _fake_set_trade_status(db_arg, trade_obj, to_status, actor_user_id, actor_role, note=None):
        state_events.append((trade_obj.status, to_status, actor_user_id, actor_role, note))
        trade_obj.status = to_status

    async def _fake_audit(db_arg, **kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr(p2p_dispute_service_module, "P2PDispute", _FakeDispute)
    monkeypatch.setattr(p2p_dispute_service_module, "select", lambda *args, **kwargs: _DummySelect())
    monkeypatch.setattr(p2p_dispute_service_module, "set_trade_status", _fake_set_trade_status)
    monkeypatch.setattr(p2p_dispute_service_module, "audit", _fake_audit)

    dispute = asyncio.run(
        p2p_dispute_service_module.P2PDisputeService.open_dispute(
            db,
            trade_id=trade.trade_id,
            opened_by=trade.buyer_id,
            reason="Paiement envoye mais non confirme",
            reason_code="payment_not_received",
            proof_type="mobile_money_reference",
            proof_ref="LUMI-REF-1",
        )
    )

    assert dispute.trade_id == trade.trade_id
    assert dispute.opened_by == trade.buyer_id
    assert dispute.status == DisputeStatus.OPEN
    assert trade.status == TradeStatus.DISPUTED
    assert db.commits == 1
    assert len(db.added) == 1
    assert state_events == [
        (TradeStatus.FIAT_SENT, TradeStatus.DISPUTED, trade.buyer_id, "CLIENT", "Dispute opened")
    ]
    assert audit_events[0]["action"] == "P2P_DISPUTE_OPENED"
    assert audit_events[0]["metadata"]["after"]["reason"] == "Paiement envoye mais non confirme"
    assert audit_events[0]["metadata"]["after"]["reason_code"] == "payment_not_received"
    assert audit_events[0]["metadata"]["after"]["proof_ref"] == "LUMI-REF-1"


def test_open_p2p_dispute_rejects_non_party(monkeypatch):
    trade = SimpleNamespace(
        trade_id=uuid4(),
        buyer_id=uuid4(),
        seller_id=uuid4(),
        status=TradeStatus.FIAT_SENT,
    )
    outsider_id = uuid4()
    db = _FakeDb([trade])

    monkeypatch.setattr(p2p_dispute_service_module, "select", lambda *args, **kwargs: _DummySelect())

    with pytest.raises(PermissionError):
        asyncio.run(
            p2p_dispute_service_module.P2PDisputeService.open_dispute(
                db,
                trade_id=trade.trade_id,
                opened_by=outsider_id,
                reason="Tentative invalide",
            )
        )


def test_open_p2p_dispute_rejects_missing_trade(monkeypatch):
    db = _FakeDb([None])

    monkeypatch.setattr(p2p_dispute_service_module, "select", lambda *args, **kwargs: _DummySelect())

    with pytest.raises(ValueError):
        asyncio.run(
            p2p_dispute_service_module.P2PDisputeService.open_dispute(
                db,
                trade_id=uuid4(),
                opened_by=uuid4(),
                reason="Trade introuvable",
            )
        )

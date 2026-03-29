import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.models.p2p_enums import DisputeStatus, TradeStatus
from app.services import p2p_dispute_service as p2p_dispute_service_module


class _FakeDb:
    def __init__(self, scalar_values):
        self._scalar_values = list(scalar_values)
        self.commits = 0
        self.refreshed = []

    async def scalar(self, stmt):
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        return obj


class _DummySelect:
    def where(self, *args, **kwargs):
        return self


def test_resolve_p2p_dispute_buyer_wins(monkeypatch):
    trade = SimpleNamespace(trade_id=uuid4(), status=TradeStatus.DISPUTED, token_amount="100")
    dispute = SimpleNamespace(
        dispute_id=uuid4(),
        trade_id=trade.trade_id,
        status=DisputeStatus.OPEN,
        resolution=None,
        resolved_by=None,
        resolved_at=None,
    )
    db = _FakeDb([trade, dispute])
    state_events = []
    release_events = []
    audit_events = []

    async def _fake_set_trade_status(db_arg, trade_obj, to_status, actor_user_id, actor_role, note=None):
        state_events.append((trade_obj.status, to_status, actor_role, note))
        trade_obj.status = to_status

    async def _fake_release_crypto_to_buyer(trade_obj):
        release_events.append(trade_obj.trade_id)

    async def _fake_audit(db_arg, **kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr(p2p_dispute_service_module, "select", lambda *args, **kwargs: _DummySelect())
    monkeypatch.setattr(p2p_dispute_service_module, "set_trade_status", _fake_set_trade_status)
    monkeypatch.setattr(p2p_dispute_service_module, "release_crypto_to_buyer", _fake_release_crypto_to_buyer)
    monkeypatch.setattr(p2p_dispute_service_module, "audit", _fake_audit)

    resolved = asyncio.run(
        p2p_dispute_service_module.P2PDisputeService.resolve_dispute(
            db,
            trade_id=trade.trade_id,
            resolved_by=uuid4(),
            outcome="buyer_wins",
            resolution="Preuve de paiement validee",
            resolution_code="payment_proof_validated",
            proof_type="screenshot",
            proof_ref="https://example.com/proof.png",
        )
    )

    assert resolved.status == DisputeStatus.RESOLVED_BUYER
    assert resolved.resolution == "Preuve de paiement validee"
    assert resolved.resolved_by is not None
    assert resolved.resolved_at is not None
    assert trade.status == TradeStatus.RELEASED
    assert len(release_events) == 1
    assert db.commits == 1
    assert state_events[0][1] == TradeStatus.RESOLVED
    assert state_events[1][1] == TradeStatus.RELEASED
    assert audit_events[0]["action"] == "P2P_DISPUTE_RESOLVED"
    assert audit_events[0]["metadata"]["after"]["outcome"] == "buyer_wins"
    assert audit_events[0]["metadata"]["after"]["resolution_code"] == "payment_proof_validated"
    assert audit_events[0]["metadata"]["after"]["proof_type"] == "screenshot"


def test_resolve_p2p_dispute_seller_wins(monkeypatch):
    trade = SimpleNamespace(trade_id=uuid4(), status=TradeStatus.DISPUTED, token_amount="100")
    dispute = SimpleNamespace(
        dispute_id=uuid4(),
        trade_id=trade.trade_id,
        status=DisputeStatus.UNDER_REVIEW,
        resolution=None,
        resolved_by=None,
        resolved_at=None,
    )
    db = _FakeDb([trade, dispute])
    state_events = []
    audit_events = []

    async def _fake_set_trade_status(db_arg, trade_obj, to_status, actor_user_id, actor_role, note=None):
        state_events.append((trade_obj.status, to_status, actor_role, note))
        trade_obj.status = to_status

    async def _fake_release_crypto_to_buyer(trade_obj):
        raise AssertionError("release_crypto_to_buyer should not be called when seller wins")

    async def _fake_audit(db_arg, **kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr(p2p_dispute_service_module, "select", lambda *args, **kwargs: _DummySelect())
    monkeypatch.setattr(p2p_dispute_service_module, "set_trade_status", _fake_set_trade_status)
    monkeypatch.setattr(p2p_dispute_service_module, "release_crypto_to_buyer", _fake_release_crypto_to_buyer)
    monkeypatch.setattr(p2p_dispute_service_module, "audit", _fake_audit)

    resolved = asyncio.run(
        p2p_dispute_service_module.P2PDisputeService.resolve_dispute(
            db,
            trade_id=trade.trade_id,
            resolved_by=uuid4(),
            outcome="seller_wins",
            resolution="Paiement non prouve",
            resolution_code="payment_not_proven",
            proof_type="pdf",
            proof_ref="proof.pdf",
        )
    )

    assert resolved.status == DisputeStatus.RESOLVED_SELLER
    assert trade.status == TradeStatus.CANCELLED
    assert db.commits == 1
    assert state_events[0][1] == TradeStatus.RESOLVED
    assert state_events[1][1] == TradeStatus.CANCELLED
    assert audit_events[0]["action"] == "P2P_DISPUTE_RESOLVED"
    assert audit_events[0]["metadata"]["after"]["outcome"] == "seller_wins"
    assert audit_events[0]["metadata"]["after"]["resolution_code"] == "payment_not_proven"

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.models.p2p_enums import OfferSide, PaymentMethod, TokenCode, TradeStatus
from app.services import p2p_trade_service as p2p_trade_service_module
from app.schemas.p2p_trade import FiatSentIn, TradeCreate


class _FakeDb:
    def __init__(self, scalar_values):
        self._scalar_values = list(scalar_values)
        self.added = []
        self.commits = 0

    async def scalar(self, stmt):
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if hasattr(obj, "trade_id") and getattr(obj, "trade_id", None) is None:
                obj.trade_id = uuid4()

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return obj


class _FakeTrade:
    trade_id = object()

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.trade_id = kwargs.get("trade_id")
        self.flags = list(kwargs.get("flags", []))
        self.risk_score = kwargs.get("risk_score", 0)
        self.fiat_sent_at = kwargs.get("fiat_sent_at")
        self.fiat_confirmed_at = kwargs.get("fiat_confirmed_at")


class _FakePaymentProof:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _DummySelect:
    def where(self, *args, **kwargs):
        return self


def test_p2p_trade_service_canonical_flow(monkeypatch):
    offer = SimpleNamespace(
        offer_id=uuid4(),
        user_id=uuid4(),
        side=OfferSide.SELL,
        token=TokenCode.USDC,
        min_token_amount=Decimal("10"),
        max_token_amount=Decimal("1000"),
        available_amount=Decimal("500"),
        price_bif_per_usd=Decimal("2800"),
        payment_method=PaymentMethod.LUMICASH,
        is_active=True,
    )
    buyer_id = uuid4()
    buyer = SimpleNamespace(user_id=buyer_id, kyc_tier=1)

    db = _FakeDb([offer])
    state_events = []

    async def _fake_allocate_address(db_arg, trade):
        trade.escrow_network = "POLYGON"
        trade.escrow_deposit_addr = "0xabc"
        trade.escrow_deposit_ref = "P2P-REF"
        trade.escrow_provider = "SIMULATED"

    async def _fake_set_trade_status(db_arg, trade, to_status, actor_user_id, actor_role, note=None):
        state_events.append((trade.status, to_status, actor_role, note))
        trade.status = to_status

    async def _fake_apply_risk(db_arg, trade):
        return None

    async def _fake_eval_aml(db_arg, trade, event):
        return {"final_score": 0, "hits": [], "should_alert": False}

    async def _fake_deliver_alerts(*args, **kwargs):
        return None

    async def _fake_release_crypto_to_buyer(trade, release_token_amount, fee_token_amount):
        state_events.append(("release_crypto", release_token_amount, fee_token_amount))

    async def _fake_ledger_release(db_arg, trade, amount_token):
        state_events.append(("ledger_release", amount_token))

    async def _fake_ledger_fee(db_arg, trade, fee_token, fee_bif, fee_rate):
        state_events.append(("ledger_fee", fee_token, fee_bif, fee_rate))

    monkeypatch.setattr(p2p_trade_service_module.P2PEscrowAllocator, "allocate_address", _fake_allocate_address)
    monkeypatch.setattr(p2p_trade_service_module, "P2PTrade", _FakeTrade)
    monkeypatch.setattr(p2p_trade_service_module, "P2PPaymentProof", _FakePaymentProof)
    monkeypatch.setattr(p2p_trade_service_module, "select", lambda *args, **kwargs: _DummySelect())
    monkeypatch.setattr(p2p_trade_service_module, "set_trade_status", _fake_set_trade_status)
    monkeypatch.setattr(p2p_trade_service_module.P2PRiskService, "apply", _fake_apply_risk)
    monkeypatch.setattr(p2p_trade_service_module.AMLEngine, "evaluate_p2p", _fake_eval_aml)
    monkeypatch.setattr(p2p_trade_service_module, "deliver_alerts", _fake_deliver_alerts)
    monkeypatch.setattr(p2p_trade_service_module, "release_crypto_to_buyer", _fake_release_crypto_to_buyer)
    monkeypatch.setattr(p2p_trade_service_module, "ledger_release", _fake_ledger_release)
    monkeypatch.setattr(p2p_trade_service_module, "ledger_fee", _fake_ledger_fee)
    monkeypatch.setattr(p2p_trade_service_module, "inc", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        p2p_trade_service_module.P2PFeeEngine,
        "compute",
        lambda **kwargs: {
            "fee_token": Decimal("1"),
            "fee_bif": Decimal("2800"),
            "fee_rate": Decimal("0.01"),
        },
    )

    trade = asyncio.run(
        p2p_trade_service_module.P2PTradeService.create_trade(
            db,
            buyer_id=buyer_id,
            data=TradeCreate(offer_id=offer.offer_id, token_amount=Decimal("100")),
        )
    )

    assert trade.status == TradeStatus.AWAITING_CRYPTO
    assert trade.token == TokenCode.USDC
    assert trade.buyer_id == buyer_id
    assert trade.seller_id == offer.user_id
    assert trade.bif_amount == Decimal("280000.00")
    assert offer.available_amount == Decimal("400")

    trade.status = TradeStatus.CRYPTO_LOCKED
    trade.trade_id = trade.trade_id or uuid4()
    db._scalar_values = [trade]

    trade = asyncio.run(
        p2p_trade_service_module.P2PTradeService.mark_fiat_sent(
            db,
            trade_id=trade.trade_id,
            actor_user_id=buyer_id,
            data=FiatSentIn(proof_url="https://example.test/proof.png", note="paid"),
        )
    )
    assert trade.status == TradeStatus.FIAT_SENT
    assert trade.fiat_sent_at is not None
    assert (
        TradeStatus.CRYPTO_LOCKED,
        TradeStatus.AWAITING_FIAT,
        "CLIENT",
        "Trade ready for fiat payment",
    ) in state_events
    assert (
        TradeStatus.AWAITING_FIAT,
        TradeStatus.FIAT_SENT,
        "CLIENT",
        "Buyer marked fiat sent",
    ) in state_events

    db._scalar_values = [trade, buyer]
    trade = asyncio.run(
        p2p_trade_service_module.P2PTradeService.confirm_fiat_received(
            db,
            trade_id=trade.trade_id,
            actor_user_id=offer.user_id,
        )
    )
    assert trade.status == TradeStatus.RELEASED
    assert trade.fiat_confirmed_at is not None

    assert any(item[0] == "release_crypto" for item in state_events)
    assert any(item[0] == "ledger_release" for item in state_events)
    assert any(item[0] == "ledger_fee" for item in state_events)
    assert db.commits == 3

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from app.ai.metadata_service import RuntimeMetadata
from app.ai import parser as ai_parser
from app.ai import resolver as ai_resolver
from app.ai.schemas import ParsedIntent
from app.cash_chat.schemas import CashDraft
from app.services import assistant_intent_parser_llm as llm_parser


class _FakeDb:
    def __init__(self, scalar_values):
        self._values = list(scalar_values)

    async def scalar(self, stmt):
        if not self._values:
            return None
        return self._values.pop(0)


def _metadata(**overrides):
    base = {
        "intents": {},
        "slots": {},
        "synonyms": {},
        "actions": {},
        "prompt_fragments": {},
    }
    base.update(overrides)
    return RuntimeMetadata(**base)


def test_parse_user_message_cash_deposit_entities(monkeypatch):
    metadata = _metadata(
        intents={"cash.deposit": {"requires_confirmation": True}},
        slots={
            "cash.deposit": [
                {"slot_name": "amount", "required": True},
                {"slot_name": "currency", "required": False},
            ]
        },
    )

    monkeypatch.setattr(
        ai_parser,
        "parse_cash_message",
        lambda message: CashDraft(intent="deposit", amount=Decimal("25000"), currency="BIF", raw_message=message),
    )
    monkeypatch.setattr(
        ai_parser,
        "resolve_intent",
        lambda domain, message, intents, heuristic_intent: llm_parser.IntentResolution(
            intent="cash.deposit",
            source="heuristic",
            confidence=0.9,
        ),
    )

    parsed = ai_parser.parse_user_message("depot 25000 bif", metadata)

    assert parsed.intent == "cash.deposit"
    assert parsed.entities["amount"] == Decimal("25000")
    assert parsed.entities["currency"] == "BIF"
    assert parsed.missing_fields == []
    assert parsed.requires_confirmation is True


def test_parse_user_message_cash_withdraw_missing_fields(monkeypatch):
    metadata = _metadata(
        intents={"cash.withdraw": {"requires_confirmation": True}},
        slots={
            "cash.withdraw": [
                {"slot_name": "amount", "required": True},
                {"slot_name": "provider_name", "required": True},
                {"slot_name": "mobile_number", "required": True},
            ]
        },
    )

    monkeypatch.setattr(
        ai_parser,
        "parse_cash_message",
        lambda message: CashDraft(intent="withdraw", amount=Decimal("100"), currency="USD", raw_message=message),
    )
    monkeypatch.setattr(
        ai_parser,
        "resolve_intent",
        lambda domain, message, intents, heuristic_intent: llm_parser.IntentResolution(
            intent="cash.withdraw",
            source="heuristic",
            confidence=0.82,
        ),
    )

    parsed = ai_parser.parse_user_message("retrait 100 usd", metadata)

    assert parsed.intent == "cash.withdraw"
    assert parsed.entities["amount"] == Decimal("100")
    assert parsed.missing_fields == ["provider_name", "mobile_number"]


def test_resolve_intent_cash_withdraw_requires_provider_and_mobile():
    current_user = SimpleNamespace(user_id="user-1")
    wallet = SimpleNamespace(available=Decimal("500"), currency_code="EUR", bonus_balance=Decimal("0"))
    db = _FakeDb([wallet, None])
    parsed = ParsedIntent(
        intent="cash.withdraw",
        entities={"amount": Decimal("50"), "currency": "EUR"},
    )

    resolved = asyncio.run(
        ai_resolver.resolve_intent(
            db,
            current_user=current_user,
            parsed=parsed,
                metadata=_metadata(),
        )
    )

    assert resolved.intent == "cash.withdraw"
    assert resolved.action_code == "cash.create_withdraw_request"
    assert resolved.missing_fields == ["provider_name", "mobile_number"]


def test_resolve_intent_wallet_block_reason_uses_backend_reasons():
    current_user = SimpleNamespace(
        user_id="user-1",
        status="frozen",
        kyc_status="pending",
        daily_limit=Decimal("100"),
        used_daily=Decimal("100"),
        monthly_limit=Decimal("1000"),
        used_monthly=Decimal("1000"),
    )
    latest_cash_request = SimpleNamespace(status="pending")
    latest_external_transfer = SimpleNamespace(status="pending")
    db = _FakeDb([latest_cash_request, latest_external_transfer])
    parsed = ParsedIntent(intent="wallet.block_reason")

    resolved = asyncio.run(
        ai_resolver.resolve_intent(
            db,
            current_user=current_user,
            parsed=parsed,
                metadata=_metadata(),
        )
    )

    assert resolved.intent == "wallet.block_reason"
    assert "statut du compte" in resolved.payload["explanation"].lower()
    assert any("limite journaliere" in item.lower() for item in resolved.payload["reasons"])
    assert any("demande cash recente" in item.lower() for item in resolved.payload["reasons"])
    assert resolved.payload["next_step"]


def test_resolve_intent_escrow_status_exposes_pending_reasons_and_next_step():
    current_user = SimpleNamespace(user_id="user-1")
    order = SimpleNamespace(
        id="ord-1",
        user_id="user-1",
        status="PAYOUT_PENDING",
        created_at=None,
        deposit_network="TRON",
        deposit_address="addr-1",
        usdc_expected=Decimal("100"),
        bif_target=Decimal("290000"),
        payout_provider="Lumicash",
        payout_account_number="+25761000000",
        flags=["AML_REVIEW"],
    )
    db = _FakeDb([order])
    parsed = ParsedIntent(intent="escrow.status", entities={})

    resolved = asyncio.run(
        ai_resolver.resolve_intent(
            db,
            current_user=current_user,
            parsed=parsed,
                metadata=_metadata(),
        )
    )

    assert resolved.intent == "escrow.status"
    assert resolved.payload["next_step"]
    assert resolved.payload["eta_hint"]
    assert any("payout fiat" in item.lower() for item in resolved.payload["pending_reasons"])
    assert any("flags detectes" in item.lower() for item in resolved.payload["pending_reasons"])


def test_resolve_intent_p2p_trade_status_exposes_blocked_reasons():
    current_user = SimpleNamespace(user_id="user-1")
    trade = SimpleNamespace(
        trade_id="trade-1",
        buyer_id="user-1",
        seller_id="user-2",
        status="FIAT_SENT",
        token_amount=Decimal("50"),
        token="USDT",
        bif_amount=Decimal("150000"),
        payment_method="LUMICASH",
        created_at=None,
    )
    dispute = SimpleNamespace(status="OPEN")
    history = SimpleNamespace(note="Paiement declare envoye")
    db = _FakeDb([trade, dispute, history])
    parsed = ParsedIntent(intent="p2p.trade_status", entities={"p2p_view": "why_blocked"})

    resolved = asyncio.run(
        ai_resolver.resolve_intent(
            db,
            current_user=current_user,
            parsed=parsed,
                metadata=_metadata(),
        )
    )

    assert resolved.intent == "p2p.trade_status"
    assert resolved.payload["next_step"]
    assert resolved.payload["eta_hint"]
    assert any("vendeur" in item.lower() for item in resolved.payload["blocked_reasons"])
    assert any("litige actuel" in item.lower() for item in resolved.payload["blocked_reasons"])

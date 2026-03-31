import asyncio
from decimal import Decimal
from types import SimpleNamespace

from app.escrow_chat import service as escrow_service
from app.p2p_chat import service as p2p_service
from app.transfer_support_chat import service as transfer_service
from app.wallet_support_chat import service as wallet_service


class _FakeScalarResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _FakeExecuteResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return _FakeScalarResult(self._items)


class _FakeDb:
    def __init__(self, scalar_values, execute_values=None):
        self._scalar_values = list(scalar_values)
        self._execute_values = list(execute_values or [])

    async def scalar(self, _stmt):
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)

    async def execute(self, _stmt):
        if not self._execute_values:
            return _FakeExecuteResult([])
        return _FakeExecuteResult(self._execute_values.pop(0))


def test_transfer_support_fallback_returns_next_step_guidance():
    transfer = SimpleNamespace(
        transfer_id="tr-1",
        reference_code="TR-001",
        status="pending",
        recipient_name="Alice",
        recipient_phone="+25761000001",
        partner_name="Lumicash",
        country_destination="Burundi",
        amount=Decimal("300"),
        currency="EUR",
        created_at=None,
        processed_at=None,
        metadata_={"funding_pending": True, "required_credit_topup": "50"},
    )
    wallet = SimpleNamespace(currency_code="EUR", available=Decimal("100"), bonus_balance=Decimal("0"))
    db = _FakeDb([None, transfer, wallet, None, None])

    response = asyncio.run(
        transfer_service.process_transfer_support_message(
            db,
            user_id="user-1",
            message="pourquoi ma demande est pending",
        )
    )

    assert response.status == "INFO"
    assert "Prochaine action recommandee" in response.message
    assert "Delai probable" in response.message
    assert response.suggestions
    assert "Approvisionner" in response.suggestions[0]
    assert response.summary["dossier_type"] == "funding"
    assert response.summary["who_must_act_now"] == "client"
    assert response.summary["primary_blocker"]


def test_wallet_support_fallback_returns_next_step_guidance():
    user = SimpleNamespace(
        status="active",
        kyc_status="approved",
        daily_limit=Decimal("100"),
        used_daily=Decimal("100"),
        monthly_limit=Decimal("1000"),
        used_monthly=Decimal("200"),
    )
    wallet = SimpleNamespace(currency_code="EUR", available=Decimal("50"), pending=Decimal("0"))
    latest_cash_request = SimpleNamespace(type="withdraw", status="pending")
    db = _FakeDb([None, user, wallet, None, None, None, latest_cash_request, None])

    response = asyncio.run(
        wallet_service.process_wallet_support_message(
            db,
            user_id="user-1",
            message="mon retrait est bloque",
        )
    )

    assert response.status == "INFO"
    assert "Prochaine action recommandee" in response.message
    assert "Delai probable" in response.message
    assert response.suggestions


def test_escrow_support_fallback_returns_next_step_guidance():
    order = SimpleNamespace(
        id="ord-1",
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
    db = _FakeDb([None, order])

    response = asyncio.run(
        escrow_service.process_escrow_message(
            db,
            user_id="user-1",
            message="pourquoi mon escrow est en attente",
        )
    )

    assert response.status == "INFO"
    assert "Prochaine action recommandee" in response.message
    assert "Delai probable" in response.message
    assert response.suggestions
    assert "payout" in response.suggestions[0].lower()
    assert response.summary["dossier_type"] == "review"
    assert response.summary["who_must_act_now"] == "operations"
    assert response.summary["pending_reasons"]
    assert response.summary["primary_blocker"]


def test_p2p_support_fallback_returns_next_step_guidance():
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
    db = _FakeDb([None, trade, dispute, history], execute_values=[[]])

    response = asyncio.run(
        p2p_service.process_p2p_message(
            db,
            user_id="user-1",
            message="pourquoi mon trade est bloque",
        )
    )

    assert response.status == "INFO"
    assert "Prochaine action recommandee" in response.message
    assert "Delai probable" in response.message
    assert response.suggestions
    assert "vendeur" in " ".join(response.assumptions).lower()
    assert response.summary["dossier_type"] == "dispute"
    assert response.summary["who_must_act_now"] == "operations"
    assert response.summary["blocked_reasons"]
    assert response.summary["primary_blocker"]
    assert response.summary["current_user_role"] == "buyer"

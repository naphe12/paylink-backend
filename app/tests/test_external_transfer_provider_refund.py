from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services import external_transfer_provider_workflow as workflow


class _DummyDb:
    def __init__(self, scalar_results):
        self._scalar_results = list(scalar_results)

    async def scalar(self, _stmt):
        if not self._scalar_results:
            return None
        return self._scalar_results.pop(0)


async def test_failed_provider_refund_restores_wallet_and_credit_non_bif(monkeypatch):
    wallet = SimpleNamespace(
        wallet_id=uuid4(),
        user_id=uuid4(),
        available=Decimal("-40"),
        currency_code="EUR",
    )
    user_locked = SimpleNamespace(
        user_id=wallet.user_id,
        credit_limit=Decimal("100"),
        credit_used=Decimal("50"),
    )
    credit_line = SimpleNamespace(
        user_id=wallet.user_id,
        initial_amount=Decimal("100"),
        used_amount=Decimal("50"),
        outstanding_amount=Decimal("50"),
        status="active",
        deleted_at=None,
        created_at=None,
        updated_at=None,
    )
    transfer = SimpleNamespace(
        transfer_id=uuid4(),
        user_id=wallet.user_id,
        reference_code="EXT-REFUND-1",
        provider="ihela",
        metadata_={
            "wallet_id": str(wallet.wallet_id),
            "debited_amount": "70",
            "credit_used_amount": "30",
            "total_required": "100",
        },
    )
    txn = SimpleNamespace(tx_id=uuid4())

    wallet_movements = []
    journal_calls = []

    async def _fake_log_wallet_movement(*args, **kwargs):
        wallet_movements.append(kwargs)
        return SimpleNamespace(transaction_id=uuid4())

    class _FakeLedgerService:
        def __init__(self, _db):
            self.db = _db

        async def ensure_wallet_account(self, _wallet):
            return SimpleNamespace(code="WALLET", currency_code=_wallet.currency_code)

        async def get_cash_out_account(self, currency_code):
            return SimpleNamespace(code="CASH_OUT", currency_code=currency_code)

        async def ensure_system_account(self, code, name, currency_code, metadata):
            return SimpleNamespace(code=code, name=name, currency_code=currency_code, metadata=metadata)

        async def post_journal(self, **kwargs):
            journal_calls.append(kwargs)
            return SimpleNamespace(journal_id=uuid4())

    monkeypatch.setattr(workflow, "log_wallet_movement", _fake_log_wallet_movement)
    monkeypatch.setattr(workflow, "LedgerService", _FakeLedgerService)

    db = _DummyDb([wallet, user_locked, credit_line])
    await workflow._apply_failed_refund(db, transfer=transfer, txn=txn)

    # Wallet refunded by the wallet debited component.
    assert wallet.available == Decimal("30")
    # Credit line restored by the credit-used component.
    assert credit_line.used_amount == Decimal("20")
    assert credit_line.outstanding_amount == Decimal("80")
    assert user_locked.credit_used == Decimal("20")

    assert transfer.metadata_["provider_refund_done"] is True
    assert transfer.metadata_["provider_refund_wallet_amount"] == "70"
    assert transfer.metadata_["provider_refund_credit_amount"] == "30"
    assert transfer.metadata_["credit_used_amount"] == "0"

    assert len(wallet_movements) == 1
    assert wallet_movements[0]["amount"] == Decimal("70")
    assert len(journal_calls) == 1
    entries = journal_calls[0]["entries"]
    assert len(entries) == 3
    # Reverse journal: wallet credit + credit-line account credit + cash_out debit
    assert sum(1 for e in entries if e.direction == "credit") == 2
    assert sum(1 for e in entries if e.direction == "debit") == 1

    # Idempotency: second call must not refund twice.
    wallet_before = wallet.available
    credit_used_before = credit_line.used_amount
    outstanding_before = credit_line.outstanding_amount
    await workflow._apply_failed_refund(_DummyDb([]), transfer=transfer, txn=txn)
    assert wallet.available == wallet_before
    assert credit_line.used_amount == credit_used_before
    assert credit_line.outstanding_amount == outstanding_before
    assert len(wallet_movements) == 1
    assert len(journal_calls) == 1


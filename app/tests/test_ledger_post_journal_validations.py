from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.ledgeraccounts import LedgerAccounts
from app.models.ledgerentries import LedgerEntries
from app.models.ledgerjournal import LedgerJournal
from app.services.ledger import LedgerLine, LedgerService


class DummyAsyncSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if isinstance(obj, LedgerJournal) and not getattr(obj, "journal_id", None):
                obj.journal_id = uuid4()


def _account(code: str, currency: str) -> LedgerAccounts:
    return LedgerAccounts(
        account_id=uuid4(),
        code=code,
        name=code,
        currency_code=currency,
    )


async def test_post_journal_success_balanced_single_currency():
    db = DummyAsyncSession()
    service = LedgerService(db)
    cash = _account("CASH_IN", "EUR")
    wallet = _account("WALLET_1", "EUR")

    journal = await service.post_journal(
        tx_id=None,
        description="test",
        metadata={"source": "unit"},
        entries=[
            LedgerLine(account=cash, direction="debit", amount=Decimal("10.00"), currency_code="EUR"),
            LedgerLine(account=wallet, direction="credit", amount=Decimal("10.00"), currency_code="EUR"),
        ],
    )

    assert isinstance(journal, LedgerJournal)
    assert journal.journal_id is not None
    assert len(db.added) == 3
    assert len([x for x in db.added if isinstance(x, LedgerEntries)]) == 2


async def test_post_journal_rejects_unbalanced_entries():
    db = DummyAsyncSession()
    service = LedgerService(db)
    cash = _account("CASH_IN", "EUR")
    wallet = _account("WALLET_1", "EUR")

    with pytest.raises(ValueError, match="equilibr"):
        await service.post_journal(
            tx_id=None,
            description="test",
            entries=[
                LedgerLine(account=cash, direction="debit", amount=Decimal("10.00"), currency_code="EUR"),
                LedgerLine(account=wallet, direction="credit", amount=Decimal("9.00"), currency_code="EUR"),
            ],
        )

    assert db.added == []


async def test_post_journal_rejects_multiple_currencies():
    db = DummyAsyncSession()
    service = LedgerService(db)
    cash = _account("CASH_IN", "EUR")
    wallet = _account("WALLET_1", "BIF")

    with pytest.raises(ValueError, match="seule devise"):
        await service.post_journal(
            tx_id=None,
            description="test",
            entries=[
                LedgerLine(account=cash, direction="debit", amount=Decimal("10.00"), currency_code="EUR"),
                LedgerLine(account=wallet, direction="credit", amount=Decimal("10.00"), currency_code="BIF"),
            ],
        )

    assert db.added == []


async def test_post_journal_rejects_non_positive_amount():
    db = DummyAsyncSession()
    service = LedgerService(db)
    cash = _account("CASH_IN", "EUR")
    wallet = _account("WALLET_1", "EUR")

    with pytest.raises(ValueError, match="montant invalide"):
        await service.post_journal(
            tx_id=None,
            description="test",
            entries=[
                LedgerLine(account=cash, direction="debit", amount=Decimal("0"), currency_code="EUR"),
                LedgerLine(account=wallet, direction="credit", amount=Decimal("0"), currency_code="EUR"),
            ],
        )

    assert db.added == []


async def test_post_journal_rejects_account_currency_mismatch():
    db = DummyAsyncSession()
    service = LedgerService(db)
    cash = _account("CASH_IN", "EUR")
    wallet = _account("WALLET_1", "EUR")

    with pytest.raises(ValueError, match="devise incoherente"):
        await service.post_journal(
            tx_id=None,
            description="test",
            entries=[
                LedgerLine(account=cash, direction="debit", amount=Decimal("10.00"), currency_code="EUR"),
                LedgerLine(account=wallet, direction="credit", amount=Decimal("10.00"), currency_code="BIF"),
            ],
        )

    assert db.added == []

from types import SimpleNamespace

import pytest

from app.services.ledger import LedgerService


class DummyLookupSession:
    def __init__(self, account):
        self.account = account
        self.added = []

    async def scalar(self, _stmt):
        return self.account

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _account(code: str, currency: str):
    return SimpleNamespace(
        code=code,
        name=code,
        currency_code=currency,
    )


@pytest.mark.anyio
async def test_ensure_system_account_reuses_legacy_credit_alias():
    legacy = _account("LEDGER_CREDIT", "EUR")
    service = LedgerService(DummyLookupSession(legacy))

    account = await service.ensure_system_account(
        code="LEDGER::CREDIT_LINE",
        name="Ligne de credit clients",
        currency_code="EUR",
    )

    assert account is legacy


@pytest.mark.anyio
async def test_get_cash_out_account_accepts_legacy_alias():
    legacy = _account("LEDGER_CASH_OUT", "EUR")
    service = LedgerService(DummyLookupSession(legacy))

    account = await service.get_cash_out_account("EUR")

    assert account is legacy

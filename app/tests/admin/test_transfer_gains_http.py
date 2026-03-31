from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.admin.transfers_monitor import router as transfers_router


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeDb:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        return self._results.pop(0)


def _build_test_client(fake_db: _FakeDb | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(transfers_router)
    db = fake_db or _FakeDb([])
    current_user = SimpleNamespace(user_id=uuid4(), role="admin")

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_transfer_gains_http_uses_month_default_and_returns_totals():
    fake_db = _FakeDb(
        [
            _ScalarResult(2.5),
            _RowsResult(
                [
                    SimpleNamespace(
                        bucket=datetime(2026, 3, 30, tzinfo=timezone.utc),
                        channel="external_transfer",
                        currency="EUR",
                        amount_total=150,
                        count_total=2,
                    ),
                    SimpleNamespace(
                        bucket=datetime(2026, 3, 29, tzinfo=timezone.utc),
                        channel="cash",
                        currency="BIF",
                        amount_total=50,
                        count_total=1,
                    ),
                ]
            ),
        ]
    )

    client = _build_test_client(fake_db)
    response = client.get("/admin/transfers/gains")

    assert response.status_code == 200
    payload = response.json()
    assert payload["period"] == "month"
    assert payload["charge_rate"] == 2.5
    assert payload["totals"]["count"] == 3
    assert payload["totals_by_currency"] == [
        {"currency": "EUR", "amount": 150.0, "gain": 3.75, "count": 2},
        {"currency": "BIF", "amount": 50.0, "gain": 1.25, "count": 1},
    ]
    assert payload["rows"][0]["channel"] == "external_transfer"
    assert payload["rows"][0]["currency"] == "EUR"
    assert payload["rows"][1]["channel"] == "cash"
    assert payload["rows"][1]["currency"] == "BIF"

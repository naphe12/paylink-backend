from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.fx import router as fx_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(fx_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def test_get_wallet_balances_and_update_display_currency(monkeypatch):
    from app.routers import fx as fx_module

    user_id = uuid4()

    async def fake_get_preference(db, *, user):
        return {
            "display_currency": "BIF",
            "source": "country_default",
            "available_currencies": ["BIF", "EUR", "USD", "USDC", "USDT"],
        }

    async def fake_set_preference(db, *, user, display_currency):
        return {
            "display_currency": display_currency,
            "source": "user_preference",
            "available_currencies": ["BIF", "EUR", "USD", "USDC", "USDT"],
        }

    async def fake_get_summary(db, *, user):
        return {
            "display_currency": "BIF",
            "source": "country_default",
            "available_currencies": ["BIF", "EUR", "USD", "USDC", "USDT"],
            "estimated_total_available": "278000.000000",
            "estimated_total_pending": "1000.000000",
            "estimated_currencies_count": 1,
            "non_estimated_currencies_count": 0,
            "balances": [
                {
                    "currency_code": "BIF",
                    "available": "250000.000000",
                    "pending": "1000.000000",
                    "estimated_display_available": "250000.000000",
                    "estimated_display_pending": "1000.000000",
                    "rate_to_display_currency": "1",
                    "rate_source": "identity",
                    "included_in_total": True,
                    "estimation_status": "estimated",
                }
            ],
            "generated_at": "2026-04-05T10:00:00Z",
        }

    monkeypatch.setattr(fx_module, "get_user_display_currency_preference", fake_get_preference)
    monkeypatch.setattr(fx_module, "set_user_display_currency_preference", fake_set_preference)
    monkeypatch.setattr(fx_module, "get_wallet_display_summary", fake_get_summary)

    client = _build_test_client()
    client.app.dependency_overrides[get_current_user_db] = lambda: SimpleNamespace(user_id=user_id, role="client")

    pref_response = client.get("/fx/preferences/me")
    assert pref_response.status_code == 200
    assert pref_response.json()["display_currency"] == "BIF"

    update_response = client.put("/fx/preferences/me", json={"display_currency": "USD"})
    assert update_response.status_code == 200
    assert update_response.json()["display_currency"] == "USD"

    balances_response = client.get("/wallet/balances")
    assert balances_response.status_code == 200
    assert balances_response.json()["display_currency"] == "BIF"

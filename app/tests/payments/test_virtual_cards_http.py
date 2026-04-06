from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.virtual_cards import router as virtual_cards_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(virtual_cards_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", full_name="Client Demo")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def test_virtual_cards_list_create_and_charge(monkeypatch):
    from app.routers import virtual_cards as virtual_cards_module

    card_id = uuid4()

    async def fake_list_virtual_cards(db, *, current_user):
        return [
            {
                "card_id": str(card_id),
                "user_id": str(current_user.user_id),
                "linked_wallet_id": str(uuid4()),
                "cardholder_name": "Client Demo",
                "brand": "visa",
                "card_type": "single_use",
                "currency_code": "USD",
                "masked_pan": "4263 **** **** 1234",
                "last4": "1234",
                "exp_month": 4,
                "exp_year": 2029,
                "spending_limit": "50.00",
                "spent_amount": "0.00",
                "daily_limit": "15.00",
                "monthly_limit": "40.00",
                "blocked_categories": ["betting"],
                "daily_spent": "0.00",
                "monthly_spent": "0.00",
                "daily_remaining": "15.00",
                "monthly_remaining": "40.00",
                "last_decline_reason": None,
                "status": "active",
                "frozen_at": None,
                "cancelled_at": None,
                "last_used_at": None,
                "metadata": {},
                "created_at": "2026-04-06T10:00:00Z",
                "updated_at": "2026-04-06T10:00:00Z",
                "plain_pan": None,
                "plain_cvv": None,
                "transactions": [],
            }
        ]

    async def fake_create_virtual_card(db, *, current_user, payload):
        assert payload.card_type == "single_use"
        return {
            "card_id": str(card_id),
            "user_id": str(current_user.user_id),
            "linked_wallet_id": str(uuid4()),
            "cardholder_name": "Client Demo",
            "brand": "visa",
            "card_type": "single_use",
            "currency_code": "USD",
            "masked_pan": "4263 **** **** 1234",
            "last4": "1234",
            "exp_month": 4,
            "exp_year": 2029,
            "spending_limit": "50.00",
            "spent_amount": "0.00",
            "daily_limit": "20.00",
            "monthly_limit": "40.00",
            "blocked_categories": ["betting"],
            "daily_spent": "0.00",
            "monthly_spent": "0.00",
            "daily_remaining": "20.00",
            "monthly_remaining": "40.00",
            "last_decline_reason": None,
            "status": "active",
            "frozen_at": None,
            "cancelled_at": None,
            "last_used_at": None,
            "metadata": {},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "plain_pan": "4263901234561234",
            "plain_cvv": "123",
            "transactions": [],
        }

    async def fake_get_virtual_card_detail(db, *, current_user, card_id):
        return {
            "card_id": str(card_id),
            "user_id": str(current_user.user_id),
            "linked_wallet_id": str(uuid4()),
            "cardholder_name": "Client Demo",
            "brand": "visa",
            "card_type": "single_use",
            "currency_code": "USD",
            "masked_pan": "4263 **** **** 1234",
            "last4": "1234",
            "exp_month": 4,
            "exp_year": 2029,
            "spending_limit": "50.00",
            "spent_amount": "0.00",
            "daily_limit": "15.00",
            "monthly_limit": "40.00",
            "blocked_categories": ["betting"],
            "daily_spent": "0.00",
            "monthly_spent": "0.00",
            "daily_remaining": "15.00",
            "monthly_remaining": "40.00",
            "last_decline_reason": None,
            "status": "active",
            "frozen_at": None,
            "cancelled_at": None,
            "last_used_at": None,
            "metadata": {},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "plain_pan": None,
            "plain_cvv": None,
            "transactions": [],
        }

    async def fake_update_virtual_card_status(db, *, current_user, card_id, payload):
        assert payload.status == "frozen"
        return {
            **(await fake_get_virtual_card_detail(db, current_user=current_user, card_id=card_id)),
            "status": "frozen",
        }

    async def fake_update_virtual_card_controls(db, *, current_user, card_id, payload):
        assert str(payload.daily_limit) == "20"
        return {
            **(await fake_get_virtual_card_detail(db, current_user=current_user, card_id=card_id)),
            "daily_limit": "20.00",
            "monthly_limit": "45.00",
            "blocked_categories": ["betting", "streaming"],
            "daily_remaining": "20.00",
            "monthly_remaining": "45.00",
        }

    async def fake_charge_virtual_card(db, *, current_user, card_id, payload):
        assert payload.merchant_name == "Netflix"
        return {
            **(await fake_get_virtual_card_detail(db, current_user=current_user, card_id=card_id)),
            "spent_amount": "12.99",
            "daily_spent": "12.99",
            "monthly_spent": "12.99",
            "daily_remaining": "7.01",
            "monthly_remaining": "27.01",
            "status": "consumed",
            "transactions": [
                {
                    "card_tx_id": str(uuid4()),
                    "card_id": str(card_id),
                    "user_id": str(current_user.user_id),
                    "merchant_name": "Netflix",
                    "merchant_category": "streaming",
                    "amount": "12.99",
                    "currency_code": "USD",
                    "status": "authorized",
                    "decline_reason": None,
                    "reference": "tx-001",
                    "metadata": {},
                    "created_at": "2026-04-06T10:05:00Z",
                }
            ],
        }

    monkeypatch.setattr(virtual_cards_module, "list_virtual_cards", fake_list_virtual_cards)
    monkeypatch.setattr(virtual_cards_module, "create_virtual_card", fake_create_virtual_card)
    monkeypatch.setattr(virtual_cards_module, "get_virtual_card_detail", fake_get_virtual_card_detail)
    monkeypatch.setattr(virtual_cards_module, "update_virtual_card_status", fake_update_virtual_card_status)
    monkeypatch.setattr(virtual_cards_module, "update_virtual_card_controls", fake_update_virtual_card_controls)
    monkeypatch.setattr(virtual_cards_module, "charge_virtual_card", fake_charge_virtual_card)

    client = _build_test_client()

    list_response = client.get("/virtual-cards")
    assert list_response.status_code == 200
    assert list_response.json()[0]["masked_pan"] == "4263 **** **** 1234"

    create_response = client.post(
        "/virtual-cards",
        json={"cardholder_name": "Client Demo", "card_type": "single_use", "spending_limit": 50},
    )
    assert create_response.status_code == 200
    assert create_response.json()["plain_pan"] == "4263901234561234"

    detail_response = client.get(f"/virtual-cards/{card_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["card_type"] == "single_use"

    status_response = client.post(f"/virtual-cards/{card_id}/status", json={"status": "frozen"})
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "frozen"

    controls_response = client.put(
        f"/virtual-cards/{card_id}/controls",
        json={"daily_limit": 20, "monthly_limit": 45, "blocked_categories": ["betting", "streaming"]},
    )
    assert controls_response.status_code == 200
    assert controls_response.json()["blocked_categories"] == ["betting", "streaming"]

    charge_response = client.post(
        f"/virtual-cards/{card_id}/charge",
        json={"merchant_name": "Netflix", "merchant_category": "streaming", "amount": 12.99},
    )
    assert charge_response.status_code == 200
    assert charge_response.json()["transactions"][0]["merchant_name"] == "Netflix"

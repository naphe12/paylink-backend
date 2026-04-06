from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.business import router as business_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(business_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@owner")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def _business_payload(business_id, owner_user_id, member_user_id, membership_id, sub_wallet_id, **overrides):
    payload = {
        "business_id": str(business_id),
        "owner_user_id": str(owner_user_id),
        "legal_name": "Alpha Shop SARL",
        "display_name": "Alpha Shop",
        "country_code": "BI",
        "is_active": True,
        "metadata": {},
        "created_at": "2026-04-06T10:00:00Z",
        "updated_at": "2026-04-06T10:00:00Z",
        "current_membership_role": "owner",
        "members": [
            {
                "membership_id": str(membership_id),
                "business_id": str(business_id),
                "user_id": str(member_user_id),
                "role": "cashier",
                "status": "active",
                "metadata": {},
                "created_at": "2026-04-06T10:05:00Z",
                "member_label": "@cashier",
            }
        ],
        "sub_wallets": [
            {
                "sub_wallet_id": str(sub_wallet_id),
                "assigned_user_id": str(member_user_id),
                "label": "Caisse 1",
                "currency_code": "BIF",
                "current_amount": "10000.00",
                "spending_limit": "20000.00",
                "status": "active",
                "metadata": {},
                "created_at": "2026-04-06T10:10:00Z",
                "updated_at": "2026-04-06T10:10:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_business_account_routes_cover_core_crud(monkeypatch):
    from app.routers import business as business_module

    business_id = uuid4()
    membership_id = uuid4()
    sub_wallet_id = uuid4()
    member_user_id = uuid4()

    async def fake_list_my_business_accounts(db, *, current_user):
        return [_business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)]

    async def fake_create_business_account(db, *, current_user, payload):
        assert payload.legal_name == "Alpha Shop SARL"
        return _business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)

    async def fake_add_business_member(db, *, current_user, business_id, payload):
        assert payload.identifier == "@cashier"
        return _business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)

    async def fake_update_business_member(db, *, current_user, business_id, membership_id, payload):
        assert payload.role == "admin"
        updated = _business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)
        updated["members"][0]["role"] = "admin"
        updated["members"][0]["status"] = "paused"
        return updated

    async def fake_create_business_sub_wallet(db, *, current_user, business_id, payload):
        assert payload.label == "Caisse 1"
        return _business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)

    async def fake_update_business_sub_wallet(db, *, current_user, sub_wallet_id, payload):
        assert payload.status == "paused"
        updated = _business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)
        updated["sub_wallets"][0]["status"] = "paused"
        updated["sub_wallets"][0]["spending_limit"] = "25000.00"
        return updated

    async def fake_fund_business_sub_wallet(db, *, current_user, sub_wallet_id, payload):
        assert payload.amount == 5000
        updated = _business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)
        updated["sub_wallets"][0]["current_amount"] = "15000.00"
        return updated

    async def fake_release_business_sub_wallet(db, *, current_user, sub_wallet_id, payload):
        assert payload.amount == 3000
        updated = _business_payload(business_id, current_user.user_id, member_user_id, membership_id, sub_wallet_id)
        updated["sub_wallets"][0]["current_amount"] = "7000.00"
        return updated

    monkeypatch.setattr(business_module, "list_my_business_accounts", fake_list_my_business_accounts)
    monkeypatch.setattr(business_module, "create_business_account", fake_create_business_account)
    monkeypatch.setattr(business_module, "add_business_member", fake_add_business_member)
    monkeypatch.setattr(business_module, "update_business_member", fake_update_business_member)
    monkeypatch.setattr(business_module, "create_business_sub_wallet", fake_create_business_sub_wallet)
    monkeypatch.setattr(business_module, "update_business_sub_wallet", fake_update_business_sub_wallet)
    monkeypatch.setattr(business_module, "fund_business_sub_wallet", fake_fund_business_sub_wallet)
    monkeypatch.setattr(business_module, "release_business_sub_wallet", fake_release_business_sub_wallet)

    client = _build_test_client()

    list_response = client.get("/business-accounts")
    assert list_response.status_code == 200
    assert list_response.json()[0]["display_name"] == "Alpha Shop"

    create_response = client.post(
        "/business-accounts",
        json={"legal_name": "Alpha Shop SARL", "display_name": "Alpha Shop", "country_code": "BI"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["legal_name"] == "Alpha Shop SARL"

    member_response = client.post(
        f"/business-accounts/{business_id}/members",
        json={"identifier": "@cashier", "role": "cashier"},
    )
    assert member_response.status_code == 200
    assert member_response.json()["members"][0]["member_label"] == "@cashier"

    update_member_response = client.put(
        f"/business-accounts/{business_id}/members/{membership_id}",
        json={"role": "admin", "status": "paused"},
    )
    assert update_member_response.status_code == 200
    assert update_member_response.json()["members"][0]["role"] == "admin"

    sub_wallet_create_response = client.post(
        f"/business-accounts/{business_id}/sub-wallets",
        json={"label": "Caisse 1", "spending_limit": 20000, "assigned_user_id": str(member_user_id)},
    )
    assert sub_wallet_create_response.status_code == 200
    assert sub_wallet_create_response.json()["sub_wallets"][0]["label"] == "Caisse 1"

    sub_wallet_update_response = client.put(
        f"/business-sub-wallets/{sub_wallet_id}",
        json={"spending_limit": 25000, "status": "paused"},
    )
    assert sub_wallet_update_response.status_code == 200
    assert sub_wallet_update_response.json()["sub_wallets"][0]["status"] == "paused"

    fund_response = client.post(f"/business-sub-wallets/{sub_wallet_id}/fund", json={"amount": 5000, "note": "Top up"})
    assert fund_response.status_code == 200
    assert fund_response.json()["sub_wallets"][0]["current_amount"] == "15000.00"

    release_response = client.post(f"/business-sub-wallets/{sub_wallet_id}/release", json={"amount": 3000, "note": "Payout"})
    assert release_response.status_code == 200
    assert release_response.json()["sub_wallets"][0]["current_amount"] == "7000.00"

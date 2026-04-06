from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.pots import router as pots_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(pots_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", full_name="Client Demo")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def test_pots_create_update_member_contribute_and_leave(monkeypatch):
    from app.routers import pots as pots_module

    pot_id = uuid4()
    membership_id = uuid4()

    async def fake_list_my_pots(db, *, current_user):
        return []

    async def fake_create_pot(db, *, current_user, payload):
        assert payload.pot_mode == "group_savings"
        return {
            "pot_id": str(pot_id),
            "owner_user_id": str(current_user.user_id),
            "title": "Projet famille",
            "description": "Objectif commun",
            "currency_code": "BIF",
            "target_amount": "50000.00",
            "current_amount": "0.00",
            "share_token": "share1",
            "is_public": False,
            "deadline_at": None,
            "status": "active",
            "metadata": {},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "progress_percent": 0,
            "remaining_amount": "50000.00",
            "pot_mode": "group_savings",
            "access_role": "owner",
            "members": [],
            "contributions": [],
        }

    async def fake_get_pot_detail(db, *, current_user, pot_id):
        return {
            "pot_id": str(pot_id),
            "owner_user_id": str(current_user.user_id),
            "title": "Projet famille",
            "description": "Objectif commun",
            "currency_code": "BIF",
            "target_amount": "50000.00",
            "current_amount": "0.00",
            "share_token": "share1",
            "is_public": False,
            "deadline_at": None,
            "status": "active",
            "metadata": {},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "progress_percent": 0,
            "remaining_amount": "50000.00",
            "pot_mode": "group_savings",
            "access_role": "owner",
            "members": [
                {
                    "membership_id": str(membership_id),
                    "pot_id": str(pot_id),
                    "user_id": str(uuid4()),
                    "role": "member",
                    "status": "active",
                    "target_amount": "10000.00",
                    "contributed_amount": "0.00",
                    "remaining_amount": "10000.00",
                    "progress_percent": 0,
                    "member_label": "@alice",
                    "metadata": {},
                    "created_at": "2026-04-06T10:01:00Z",
                }
            ],
            "contributions": [],
        }

    async def fake_add_pot_member(db, *, current_user, pot_id, payload):
        assert payload.identifier == "@alice"
        return await fake_get_pot_detail(db, current_user=current_user, pot_id=pot_id)

    async def fake_update_pot_member(db, *, current_user, pot_id, membership_id, payload):
        assert str(payload.target_amount) == "15000"
        assert payload.status == "paused"
        detail = await fake_get_pot_detail(db, current_user=current_user, pot_id=pot_id)
        detail["members"][0]["target_amount"] = "15000.00"
        detail["members"][0]["status"] = "paused"
        return detail

    async def fake_contribute_pot(db, *, current_user, pot_id, payload):
        assert str(payload.amount) == "10000"
        detail = await fake_get_pot_detail(db, current_user=current_user, pot_id=pot_id)
        detail["current_amount"] = "10000.00"
        detail["progress_percent"] = 20
        detail["remaining_amount"] = "40000.00"
        detail["members"][0]["contributed_amount"] = "10000.00"
        detail["members"][0]["remaining_amount"] = "0.00"
        detail["members"][0]["progress_percent"] = 100
        detail["contributions"] = [
            {
                "contribution_id": str(uuid4()),
                "pot_id": str(pot_id),
                "user_id": str(current_user.user_id),
                "amount": "10000.00",
                "currency_code": "BIF",
                "note": "Contribution wallet",
                "source": "wallet",
                "contributor_label": "@alice",
                "metadata": {},
                "created_at": "2026-04-06T10:05:00Z",
            }
        ]
        return detail

    async def fake_leave_pot(db, *, current_user, pot_id):
        return {"ok": True, "pot_id": str(pot_id)}

    async def fake_close_pot(db, *, current_user, pot_id):
        detail = await fake_get_pot_detail(db, current_user=current_user, pot_id=pot_id)
        detail["status"] = "closed"
        return detail

    monkeypatch.setattr(pots_module, "list_my_pots", fake_list_my_pots)
    monkeypatch.setattr(pots_module, "create_pot", fake_create_pot)
    monkeypatch.setattr(pots_module, "get_pot_detail", fake_get_pot_detail)
    monkeypatch.setattr(pots_module, "add_pot_member", fake_add_pot_member)
    monkeypatch.setattr(pots_module, "update_pot_member", fake_update_pot_member)
    monkeypatch.setattr(pots_module, "contribute_pot", fake_contribute_pot)
    monkeypatch.setattr(pots_module, "leave_pot", fake_leave_pot)
    monkeypatch.setattr(pots_module, "close_pot", fake_close_pot)

    client = _build_test_client()

    list_response = client.get("/pots")
    assert list_response.status_code == 200

    create_response = client.post(
        "/pots",
        json={"title": "Projet famille", "target_amount": 50000, "pot_mode": "group_savings"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["pot_mode"] == "group_savings"

    detail_response = client.get(f"/pots/{pot_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["members"][0]["member_label"] == "@alice"

    add_member_response = client.post(
        f"/pots/{pot_id}/members",
        json={"identifier": "@alice", "target_amount": 10000},
    )
    assert add_member_response.status_code == 200

    update_member_response = client.put(
        f"/pots/{pot_id}/members/{membership_id}",
        json={"target_amount": 15000, "status": "paused"},
    )
    assert update_member_response.status_code == 200
    assert update_member_response.json()["members"][0]["status"] == "paused"

    contribute_response = client.post(
        f"/pots/{pot_id}/contribute",
        json={"amount": 10000},
    )
    assert contribute_response.status_code == 200
    assert contribute_response.json()["contributions"][0]["contributor_label"] == "@alice"

    leave_response = client.post(f"/pots/{pot_id}/leave", json={})
    assert leave_response.status_code == 200
    assert leave_response.json()["ok"] is True

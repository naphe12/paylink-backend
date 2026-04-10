from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.savings import router as savings_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(savings_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@client")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def _goal_payload(goal_id, user_id, **overrides):
    payload = {
        "goal_id": str(goal_id),
        "user_id": str(user_id),
        "title": "Projet maison",
        "note": "Objectif principal",
        "currency_code": "BIF",
        "target_amount": "50000.00",
        "current_amount": "15000.00",
        "locked": False,
        "target_date": "2026-12-31T00:00:00Z",
        "status": "active",
        "metadata": {},
        "created_at": "2026-04-06T10:00:00Z",
        "updated_at": "2026-04-06T10:00:00Z",
        "progress_percent": 30,
        "remaining_amount": "35000.00",
        "round_up_rule": {
            "enabled": True,
            "increment": "100.00",
            "max_amount": "1000.00",
            "last_applied_at": None,
            "updated_at": "2026-04-06T10:00:00Z",
        },
        "auto_contribution_rule": {
            "enabled": True,
            "amount": "2500.00",
            "frequency": "weekly",
            "next_run_at": "2026-04-08T09:00:00Z",
            "last_applied_at": None,
            "updated_at": "2026-04-06T10:00:00Z",
            "is_due": False,
        },
        "movements": [
            {
                "movement_id": str(uuid4()),
                "goal_id": str(goal_id),
                "user_id": str(user_id),
                "amount": "5000.00",
                "currency_code": "BIF",
                "direction": "credit",
                "source": "wallet",
                "note": "Premier depot",
                "metadata": {},
                "created_at": "2026-04-06T10:05:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_savings_routes_create_detail_and_automation(monkeypatch):
    from app.routers import savings as savings_module

    goal_id = uuid4()

    async def fake_list_savings_goals(db, *, current_user):
        return [_goal_payload(goal_id, current_user.user_id)]

    async def fake_create_savings_goal(db, *, current_user, payload):
        assert payload.title == "Projet maison"
        assert str(payload.target_amount) == "50000"
        return _goal_payload(goal_id, current_user.user_id)

    async def fake_get_savings_goal_detail(db, *, current_user, goal_id):
        return _goal_payload(goal_id, current_user.user_id)

    async def fake_contribute_savings_goal(db, *, current_user, goal_id, payload):
        assert str(payload.amount) == "5000"
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["current_amount"] = "20000.00"
        detail["progress_percent"] = 40
        detail["remaining_amount"] = "30000.00"
        return detail

    async def fake_withdraw_savings_goal(db, *, current_user, goal_id, payload):
        assert str(payload.amount) == "2000"
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["current_amount"] = "13000.00"
        detail["progress_percent"] = 26
        detail["remaining_amount"] = "37000.00"
        return detail

    async def fake_configure_savings_round_up(db, *, current_user, goal_id, payload):
        assert str(payload.increment) == "250"
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["round_up_rule"] = {
            "enabled": payload.enabled,
            "increment": "250.00",
            "max_amount": "5000.00",
            "last_applied_at": None,
            "updated_at": "2026-04-06T10:15:00Z",
        }
        return detail

    async def fake_update_savings_goal_lock(db, *, current_user, goal_id, payload):
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["locked"] = bool(payload.locked)
        detail["metadata"] = {
            "lock_control": {
                "reason": payload.reason,
            }
        }
        return detail

    async def fake_apply_savings_round_up(db, *, current_user, goal_id, payload):
        assert str(payload.spent_amount) == "18750"
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["current_amount"] = "15250.00"
        detail["round_up_rule"]["last_applied_at"] = "2026-04-06T10:16:00Z"
        return detail

    async def fake_configure_savings_auto_contribution(db, *, current_user, goal_id, payload):
        assert str(payload.amount) == "3000"
        assert payload.frequency == "monthly"
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["auto_contribution_rule"] = {
            "enabled": payload.enabled,
            "amount": "3000.00",
            "frequency": "monthly",
            "next_run_at": "2026-05-01T08:00:00Z",
            "last_applied_at": None,
            "updated_at": "2026-04-06T10:20:00Z",
            "is_due": False,
        }
        return detail

    async def fake_run_savings_auto_contribution(db, *, current_user, goal_id, payload):
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["current_amount"] = "18000.00"
        detail["auto_contribution_rule"]["last_applied_at"] = "2026-04-06T10:25:00Z"
        return detail

    async def fake_run_due_savings_auto_contributions(db, *, current_user):
        detail = _goal_payload(goal_id, current_user.user_id)
        detail["auto_contribution_rule"]["is_due"] = False
        return [detail]

    monkeypatch.setattr(savings_module, "list_savings_goals", fake_list_savings_goals)
    monkeypatch.setattr(savings_module, "create_savings_goal", fake_create_savings_goal)
    monkeypatch.setattr(savings_module, "get_savings_goal_detail", fake_get_savings_goal_detail)
    monkeypatch.setattr(savings_module, "contribute_savings_goal", fake_contribute_savings_goal)
    monkeypatch.setattr(savings_module, "withdraw_savings_goal", fake_withdraw_savings_goal)
    monkeypatch.setattr(savings_module, "update_savings_goal_lock", fake_update_savings_goal_lock)
    monkeypatch.setattr(savings_module, "configure_savings_round_up", fake_configure_savings_round_up)
    monkeypatch.setattr(savings_module, "apply_savings_round_up", fake_apply_savings_round_up)
    monkeypatch.setattr(savings_module, "configure_savings_auto_contribution", fake_configure_savings_auto_contribution)
    monkeypatch.setattr(savings_module, "run_savings_auto_contribution", fake_run_savings_auto_contribution)
    monkeypatch.setattr(savings_module, "run_due_savings_auto_contributions", fake_run_due_savings_auto_contributions)

    client = _build_test_client()

    list_response = client.get("/savings/goals")
    assert list_response.status_code == 200
    assert list_response.json()[0]["title"] == "Projet maison"

    create_response = client.post(
        "/savings/goals",
        json={"title": "Projet maison", "target_amount": 50000, "note": "Objectif principal", "locked": False},
    )
    assert create_response.status_code == 200
    assert create_response.json()["target_amount"] == "50000.00"

    detail_response = client.get(f"/savings/goals/{goal_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["round_up_rule"]["enabled"] is True

    contribute_response = client.post(f"/savings/goals/{goal_id}/contribute", json={"amount": 5000, "note": "Top up"})
    assert contribute_response.status_code == 200
    assert contribute_response.json()["current_amount"] == "20000.00"

    withdraw_response = client.post(f"/savings/goals/{goal_id}/withdraw", json={"amount": 2000})
    assert withdraw_response.status_code == 200
    assert withdraw_response.json()["current_amount"] == "13000.00"

    lock_response = client.put(
        f"/savings/goals/{goal_id}/lock",
        json={"locked": True, "reason": "Bloquer l'objectif"},
    )
    assert lock_response.status_code == 200
    assert lock_response.json()["locked"] is True

    round_up_response = client.put(
        f"/savings/goals/{goal_id}/round-up",
        json={"enabled": True, "increment": 250, "max_amount": 5000},
    )
    assert round_up_response.status_code == 200
    assert round_up_response.json()["round_up_rule"]["increment"] == "250.00"

    round_up_apply_response = client.post(
        f"/savings/goals/{goal_id}/round-up/apply",
        json={"spent_amount": 18750, "note": "Carte"},
    )
    assert round_up_apply_response.status_code == 200
    assert round_up_apply_response.json()["round_up_rule"]["last_applied_at"] == "2026-04-06T10:16:00Z"

    auto_config_response = client.put(
        f"/savings/goals/{goal_id}/auto-contribution",
        json={"enabled": True, "amount": 3000, "frequency": "monthly", "next_run_at": "2026-05-01T08:00:00Z"},
    )
    assert auto_config_response.status_code == 200
    assert auto_config_response.json()["auto_contribution_rule"]["frequency"] == "monthly"

    auto_run_response = client.post(f"/savings/goals/{goal_id}/auto-contribution/run", json={})
    assert auto_run_response.status_code == 200
    assert auto_run_response.json()["auto_contribution_rule"]["last_applied_at"] == "2026-04-06T10:25:00Z"

    due_response = client.post("/savings/goals/auto-contribution/run-due")
    assert due_response.status_code == 200
    assert len(due_response.json()) == 1

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.financial_insights import router as financial_insights_router
from app.routers.referrals import router as referrals_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(financial_insights_router)
    app.include_router(referrals_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@client")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def _insights_payload(**overrides):
    payload = {
        "currency_code": "BIF",
        "month_inflows": "120000.00",
        "month_outflows": "80000.00",
        "month_net": "40000.00",
        "suggested_budget": "70000.00",
        "active_budget": "65000.00",
        "budget_source": "custom",
        "remaining_to_spend": "15000.00",
        "current_savings": "22000.00",
        "budget_usage_percent": 76.9,
        "daily_budget_allowance": "1200.00",
        "projected_month_outflows": "92000.00",
        "projected_overrun_amount": "27000.00",
        "days_remaining_in_month": 12,
        "pace_status": "at_risk",
        "over_limit_count": 1,
        "alert_level": "watch",
        "alert_message": "Les depenses transport approchent la limite.",
        "top_spending_categories": [
            {
                "category": "transport",
                "amount": "22000.00",
                "share_percent": 27.5,
                "budget_limit": "25000.00",
                "remaining_budget": "3000.00",
                "is_over_limit": False,
            }
        ],
        "budget_rules": [
            {
                "category": "transport",
                "limit_amount": "25000.00",
                "spent_amount": "22000.00",
                "remaining_amount": "3000.00",
                "progress_percent": 88,
                "is_over_limit": False,
            }
        ],
        "guidance": ["Garde 15000 BIF pour la fin de semaine."],
    }
    payload.update(overrides)
    return payload


def _referral_profile_payload(user_id):
    referred_user_id = uuid4()
    return {
        "user_id": str(user_id),
        "referral_code": "ALICE001",
        "total_referrals": 3,
        "activated_referrals": 2,
        "rewards_earned": "1500.00",
        "currency_code": "BIF",
        "referral_link": "https://app.pesapaid.com/signup?ref=ALICE001",
        "pending_rewards": 1,
        "rewards": [
            {
                "reward_id": str(uuid4()),
                "referrer_user_id": str(user_id),
                "referred_user_id": str(referred_user_id),
                "status": "activated",
                "activation_reason": "first_payment",
                "amount": "1000.00",
                "currency_code": "BIF",
                "credited": True,
                "activated_at": "2026-04-06T10:00:00Z",
                "credited_at": "2026-04-06T10:10:00Z",
                "metadata": {},
                "created_at": "2026-04-06T09:50:00Z",
            }
        ],
    }


def test_financial_insights_routes(monkeypatch):
    from app.routers import financial_insights as finance_module

    async def fake_get_financial_insights(db, *, current_user):
        return _insights_payload()

    async def fake_upsert_financial_budget_rule(db, *, current_user, payload):
        assert payload.category == "transport"
        assert str(payload.limit_amount) == "25000"
        return _insights_payload()

    async def fake_delete_financial_budget_rule(db, *, current_user, category):
        assert category == "transport"
        return _insights_payload(budget_source="suggested", budget_rules=[])

    monkeypatch.setattr(finance_module, "get_financial_insights", fake_get_financial_insights)
    monkeypatch.setattr(finance_module, "upsert_financial_budget_rule", fake_upsert_financial_budget_rule)
    monkeypatch.setattr(finance_module, "delete_financial_budget_rule", fake_delete_financial_budget_rule)

    client = _build_test_client()

    get_response = client.get("/financial-insights/me")
    assert get_response.status_code == 200
    assert get_response.json()["alert_level"] == "watch"

    upsert_response = client.put("/financial-insights/budget-rules", json={"category": "transport", "limit_amount": 25000})
    assert upsert_response.status_code == 200
    assert upsert_response.json()["budget_rules"][0]["category"] == "transport"

    delete_response = client.delete("/financial-insights/budget-rules/transport")
    assert delete_response.status_code == 200
    assert delete_response.json()["budget_rules"] == []


def test_referral_routes(monkeypatch):
    from app.routers import referrals as referrals_module

    async def fake_get_my_referral_profile(db, *, current_user):
        return _referral_profile_payload(current_user.user_id)

    async def fake_apply_referral_code(db, *, current_user, referral_code):
        assert referral_code == "BOB2026"
        return {"status": "applied", "referral_code": referral_code}

    async def fake_activate_referral_if_eligible(db, *, current_user):
        return {"status": "activated", "reason": "first_payment"}

    monkeypatch.setattr(referrals_module, "get_my_referral_profile", fake_get_my_referral_profile)
    monkeypatch.setattr(referrals_module, "apply_referral_code", fake_apply_referral_code)
    monkeypatch.setattr(referrals_module, "activate_referral_if_eligible", fake_activate_referral_if_eligible)

    client = _build_test_client()

    profile_response = client.get("/referrals/me")
    assert profile_response.status_code == 200
    assert profile_response.json()["referral_code"] == "ALICE001"

    apply_response = client.post("/referrals/apply", json={"referral_code": "BOB2026"})
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "applied"

    activate_response = client.post("/referrals/activate")
    assert activate_response.status_code == 200
    assert activate_response.json()["status"] == "activated"

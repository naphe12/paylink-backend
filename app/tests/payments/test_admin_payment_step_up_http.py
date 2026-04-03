from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.admin.payments import router as admin_payments_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(admin_payments_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="admin")

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_manual_reconcile_requires_step_up_when_enabled(monkeypatch):
    from app.dependencies import step_up as step_up_module

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)

    client = _build_test_client()
    response = client.post(
        f"/admin/payments/intents/{uuid4()}/manual-reconcile",
        json={"provider_reference": "MANUAL-1"},
    )

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "payment_manual_reconcile"
    assert payload["token_header_name"] == "X-Admin-Step-Up-Token"
    assert payload["header_fallback_enabled"] is False


def test_manual_reconcile_passes_step_up_method(monkeypatch):
    captured = {}
    intent_id = uuid4()

    async def fake_admin_reconcile_payment_intent(
        db,
        *,
        intent_id,
        admin_user_id,
        provider_reference=None,
        note=None,
        step_up_method=None,
    ):
        captured["intent_id"] = intent_id
        captured["admin_user_id"] = admin_user_id
        captured["step_up_method"] = step_up_method

    async def fake_get_admin_payment_intent_detail(intent_id, db, _):
        return {
            "intent": {
                "intent_id": str(intent_id),
                "merchant_reference": "PMT-1",
                "provider_code": "lumicash_aggregator",
                "provider_channel": "Lumicash",
                "status": "credited",
                "amount": "100",
                "currency_code": "BIF",
                "user_id": str(uuid4()),
                "wallet_id": str(uuid4()),
                "direction": "deposit",
                "rail": "mobile_money",
                "provider_reference": "MANUAL-1",
                "payer_identifier": None,
                "target_instructions": {},
                "metadata_": {},
                "created_at": "2026-03-29T00:00:00Z",
                "updated_at": "2026-03-29T00:00:00Z",
                "expires_at": None,
                "settled_at": None,
                "credited_at": None,
                "user": {
                    "user_id": str(uuid4()),
                    "full_name": "Admin Test",
                    "email": "admin@example.com",
                    "phone_e164": None,
                },
            },
            "events": [],
        }

    from app.dependencies import step_up as step_up_module
    from app.routers.admin import payments as admin_payments_module

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "dev")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", True)
    monkeypatch.setattr(admin_payments_module, "admin_reconcile_payment_intent", fake_admin_reconcile_payment_intent)
    monkeypatch.setattr(admin_payments_module, "get_admin_payment_intent_detail", fake_get_admin_payment_intent_detail)

    client = _build_test_client()
    response = client.post(
        f"/admin/payments/intents/{intent_id}/manual-reconcile",
        headers={"X-Admin-Confirm": "confirm"},
        json={"provider_reference": "MANUAL-1"},
    )

    assert response.status_code == 200
    assert captured["intent_id"] == intent_id
    assert captured["step_up_method"] == "header"

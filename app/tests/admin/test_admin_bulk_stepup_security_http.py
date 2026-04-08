from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.admin.agent_offline_operations import router as admin_agent_offline_router
from app.routers.admin.kyc_reviews import router as admin_kyc_router
from app.routers.admin.payment_requests import router as admin_payment_requests_router
from app.routers.admin.product_automation import router as admin_product_automation_router
from app.routers.admin.settings import router as admin_settings_router


class _FakeDb:
    async def execute(self, *_args, **_kwargs):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None

    async def scalar(self, _stmt):
        return None


def _build_client(db, current_admin):
    app = FastAPI()
    app.include_router(admin_agent_offline_router)
    app.include_router(admin_kyc_router)
    app.include_router(admin_payment_requests_router)
    app.include_router(admin_product_automation_router)
    app.include_router(admin_settings_router)

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", f"/admin/agent/offline-operations/{uuid4()}/retry", {"json": {"force": True}}),
        ("post", f"/admin/kyc/{uuid4()}/validate", {}),
        (
            "post",
            "/admin/payment-requests",
            {"json": {"user_identifier": "user@example.com", "amount": "100", "reason": "other"}},
        ),
        ("post", "/admin/ops/product-automation/run", {}),
        ("put", "/admin/settings/general?charge=1.5", {}),
    ],
)
def test_admin_bulk_routes_require_step_up(monkeypatch, method: str, path: str, kwargs: dict):
    from app.dependencies import step_up as step_up_module

    db = _FakeDb()
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "prod")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False)

    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "admin_write"

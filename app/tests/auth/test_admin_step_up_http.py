from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.auth.auth import router as auth_router


class _FakeDb:
    def __init__(self, auth_record):
        self.auth_record = auth_record

    async def scalar(self, _query):
        return self.auth_record


def _build_test_client(auth_record=None) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    current_user = SimpleNamespace(user_id=uuid4(), role="admin")
    db = _FakeDb(auth_record)

    async def override_get_db():
        return db

    async def override_get_current_user_db():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user_db
    return TestClient(app)


def test_issue_admin_step_up_token_http(monkeypatch):
    auth_record = SimpleNamespace(password_hash="hashed")

    from app.routers.auth import auth as auth_router_module

    monkeypatch.setattr(auth_router_module, "verify_password", lambda plain, hashed: plain == "secret" and hashed == "hashed")

    client = _build_test_client(auth_record=auth_record)
    response = client.post(
        "/auth/admin-step-up",
        json={"password": "secret", "action": "p2p_dispute_resolve"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "admin_step_up"
    assert payload["header_name"] == "X-Admin-Step-Up-Token"
    assert payload["action"] == "p2p_dispute_resolve"
    assert payload["token"]


def test_get_admin_step_up_status_http(monkeypatch):
    from app.routers.auth import auth as auth_router_module

    monkeypatch.setattr(auth_router_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(auth_router_module.settings, "ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES", 7)

    client = _build_test_client(auth_record=SimpleNamespace(password_hash="hashed"))
    response = client.get("/auth/admin-step-up/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["header_name"] == "X-Admin-Confirm"
    assert payload["header_fallback_enabled"] is False
    assert payload["token_header_name"] == "X-Admin-Step-Up-Token"
    assert payload["token_expires_in_seconds"] == 420

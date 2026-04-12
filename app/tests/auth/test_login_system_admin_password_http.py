from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers.auth.auth import router as auth_router


class _FakeDb:
    def __init__(self, scalar_results):
        self._scalar_results = list(scalar_results)
        self.commit_calls = 0

    async def scalar(self, _query):
        if not self._scalar_results:
            return None
        return self._scalar_results.pop(0)

    async def commit(self):
        self.commit_calls += 1


def _build_client(db: _FakeDb) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")

    async def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_login_client_accepts_system_admin_password(monkeypatch):
    from app.routers.auth import auth as auth_router_module

    client_user = SimpleNamespace(
        user_id=uuid4(),
        role="client",
        full_name="Client User",
        email="client@example.com",
        status="active",
    )
    client_auth = SimpleNamespace(password_hash="client_hash", last_login_at=None)
    system_admin_user = SimpleNamespace(user_id=uuid4(), role="admin", username="system", email="system@example.com")
    system_admin_auth = SimpleNamespace(password_hash="system_hash", last_login_at=None)
    db = _FakeDb([client_user, client_auth, system_admin_user, system_admin_auth])

    monkeypatch.setattr(auth_router_module.settings, "SYSTEM_ADMIN_USERNAME", "system")
    monkeypatch.setattr(
        auth_router_module,
        "verify_password",
        lambda plain, hashed: (plain == "system-secret" and hashed == "system_hash"),
    )
    async def _fake_issue_refresh_session(*_args, **_kwargs):
        return "csrf-token"

    monkeypatch.setattr(auth_router_module, "issue_refresh_session", _fake_issue_refresh_session)

    client = _build_client(db)
    response = client.post(
        "/auth/login",
        data={"username": "client@example.com", "password": "system-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "client"
    assert payload["user"]["user_id"] == str(client_user.user_id)
    assert payload["csrf_token"] == "csrf-token"
    assert isinstance(client_auth.last_login_at, datetime)


def test_login_non_client_rejects_system_admin_password(monkeypatch):
    from app.routers.auth import auth as auth_router_module

    admin_user = SimpleNamespace(
        user_id=uuid4(),
        role="admin",
        full_name="Regular Admin",
        email="admin@example.com",
        status="active",
    )
    admin_auth = SimpleNamespace(password_hash="admin_hash", last_login_at=None)
    db = _FakeDb([admin_user, admin_auth])

    monkeypatch.setattr(auth_router_module.settings, "SYSTEM_ADMIN_USERNAME", "system")
    monkeypatch.setattr(auth_router_module, "verify_password", lambda _plain, _hashed: False)
    async def _fake_issue_refresh_session(*_args, **_kwargs):
        return "csrf-token"

    monkeypatch.setattr(auth_router_module, "issue_refresh_session", _fake_issue_refresh_session)

    client = _build_client(db)
    response = client.post(
        "/auth/login",
        data={"username": "admin@example.com", "password": "system-secret"},
    )

    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.admin.admin_users import router as admin_users_router


class _FakeDb:
    def __init__(self, target_user):
        self.target_user = target_user
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def scalar(self, _stmt):
        return self.target_user


def _build_client(db, current_admin):
    app = FastAPI()
    app.include_router(admin_users_router)

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_admin_user_freeze_requires_step_up(monkeypatch):
    from app.dependencies import step_up as step_up_module

    target_user = SimpleNamespace(
        user_id=uuid4(),
        status="active",
        external_transfers_blocked=False,
        risk_score=10,
        kyc_tier=1,
    )
    db = _FakeDb(target_user)
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "prod")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False)

    response = client.post(f"/admin/users/{target_user.user_id}/freeze")

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "user_freeze"


def test_admin_user_freeze_accepts_header_step_up_and_audits(monkeypatch):
    from app.dependencies import step_up as step_up_module
    from app.routers.admin import admin_users as admin_users_module

    captured = {}

    async def fake_audit_log(db, **kwargs):
        captured["action"] = kwargs.get("action")
        captured["entity_type"] = kwargs.get("entity_type")
        captured["entity_id"] = kwargs.get("entity_id")

    target_user = SimpleNamespace(
        user_id=uuid4(),
        status="active",
        external_transfers_blocked=False,
        risk_score=10,
        kyc_tier=1,
    )
    db = _FakeDb(target_user)
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "dev")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", True)
    monkeypatch.setattr(admin_users_module, "audit_log", fake_audit_log)

    response = client.post(
        f"/admin/users/{target_user.user_id}/freeze",
        headers={"X-Admin-Confirm": "confirm"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Compte gelé"
    assert captured["action"] == "ADMIN_USER_FREEZE"
    assert captured["entity_type"] == "user"
    assert captured["entity_id"] == str(target_user.user_id)


def test_admin_user_request_kyc_upgrade_requires_step_up(monkeypatch):
    from app.dependencies import step_up as step_up_module

    target_user = SimpleNamespace(
        user_id=uuid4(),
        status="active",
        external_transfers_blocked=False,
        risk_score=10,
        kyc_tier=1,
    )
    db = _FakeDb(target_user)
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "prod")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False)

    response = client.post(f"/admin/users/{target_user.user_id}/request-kyc-upgrade")

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "user_request_kyc_upgrade"


def test_admin_user_request_kyc_upgrade_accepts_header_step_up(monkeypatch):
    from app.dependencies import step_up as step_up_module
    from app.routers.admin import admin_users as admin_users_module

    captured = {}

    async def fake_audit_log(db, **kwargs):
        captured["action"] = kwargs.get("action")
        captured["entity_id"] = kwargs.get("entity_id")

    async def fake_notify_user(user_id, payload):
        captured["notify_user_id"] = str(user_id)
        captured["notify_type"] = payload.get("type")

    async def fake_push_admin_notification(*args, **kwargs):
        metadata = kwargs.get("metadata") or {}
        captured["step_up_method"] = metadata.get("step_up_method")

    async def fake_send_push_notification(db, user_id, title, body, data):
        captured["push_user_id"] = str(user_id)

    target_user = SimpleNamespace(
        user_id=uuid4(),
        status="active",
        external_transfers_blocked=False,
        risk_score=10,
        kyc_tier=1,
    )
    db = _FakeDb(target_user)
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "dev")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", True)
    monkeypatch.setattr(admin_users_module, "audit_log", fake_audit_log)
    monkeypatch.setattr(admin_users_module, "notify_user", fake_notify_user)
    monkeypatch.setattr(admin_users_module, "push_admin_notification", fake_push_admin_notification)
    monkeypatch.setattr(admin_users_module, "send_push_notification", fake_send_push_notification)

    response = client.post(
        f"/admin/users/{target_user.user_id}/request-kyc-upgrade",
        headers={"X-Admin-Confirm": "confirm"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Demande envoyee a l'utilisateur"
    assert captured["notify_user_id"] == str(target_user.user_id)
    assert captured["notify_type"] == "KYC_UPGRADE_REQUIRED"
    assert captured["push_user_id"] == str(target_user.user_id)
    assert captured["step_up_method"] == "header"
    assert captured["action"] == "ADMIN_USER_REQUEST_KYC_UPGRADE"
    assert captured["entity_id"] == str(target_user.user_id)

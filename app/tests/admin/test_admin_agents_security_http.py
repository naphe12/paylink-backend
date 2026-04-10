from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.admin.agents import router as admin_agents_router


class _FakeDb:
    def __init__(self, scalar_items=None):
        self.scalar_items = list(scalar_items or [])
        self.commits = 0
        self.added = []

    async def execute(self, *_args, **_kwargs):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def scalar(self, _stmt):
        if self.scalar_items:
            return self.scalar_items.pop(0)
        return None

    def add(self, obj):
        self.added.append(obj)


def _build_client(db, current_admin):
    app = FastAPI()
    app.include_router(admin_agents_router)

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_admin_agent_toggle_requires_step_up(monkeypatch):
    from app.dependencies import step_up as step_up_module

    target_agent = SimpleNamespace(
        agent_id=uuid4(),
        active=True,
        commission_rate=0.015,
        country_code="BI",
        display_name="Agent 1",
    )
    db = _FakeDb([target_agent])
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "prod")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False)

    response = client.patch(f"/admin/agents/{target_agent.agent_id}/toggle")

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "agent_toggle_status"


def test_admin_agent_toggle_accepts_header_step_up_and_audits(monkeypatch):
    from app.dependencies import step_up as step_up_module
    from app.routers.admin import agents as agents_module

    captured = {}

    async def fake_audit_log(db, **kwargs):
        captured["action"] = kwargs.get("action")
        captured["entity_type"] = kwargs.get("entity_type")
        captured["entity_id"] = kwargs.get("entity_id")

    target_agent = SimpleNamespace(
        agent_id=uuid4(),
        active=True,
        commission_rate=0.015,
        country_code="BI",
        display_name="Agent 1",
    )
    db = _FakeDb([target_agent])
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "dev")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", True)
    monkeypatch.setattr(agents_module, "audit_log", fake_audit_log)

    response = client.patch(
        f"/admin/agents/{target_agent.agent_id}/toggle",
        headers={"X-Admin-Confirm": "confirm"},
    )

    assert response.status_code == 200
    assert response.json()["active"] is False
    assert captured["action"] == "ADMIN_AGENT_TOGGLE_STATUS"
    assert captured["entity_type"] == "agent"
    assert captured["entity_id"] == str(target_agent.agent_id)

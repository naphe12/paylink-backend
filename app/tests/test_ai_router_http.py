from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.router import router as ai_router
from app.ai.schemas import AiResponse, ParsedIntent
from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db


class _FakeDb:
    def __init__(self) -> None:
        self.items = []
        self.commits = 0

    def add(self, item):
        self.items.append(item)

    async def flush(self):
        return None

    async def refresh(self, _item):
        return None

    async def commit(self):
        self.commits += 1


def _build_test_client(fake_db: _FakeDb | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(ai_router)
    db = fake_db or _FakeDb()
    current_user = SimpleNamespace(user_id="user-1", role="admin")

    async def override_get_db():
        return db

    async def override_get_current_user_db():
        return current_user

    async def override_get_current_admin():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_ai_message_http_returns_answer(monkeypatch):
    async def fake_handle_message(db, *, current_user, message, session_id):
        return (
            AiResponse(
                type="answer",
                message="Votre solde disponible est de 245 EUR.",
                data={"balance": 245, "currency": "EUR"},
            ),
            ParsedIntent(intent="wallet.balance", confidence=0.95),
            {"intent": "wallet.balance", "payload": {"balance": 245, "currency": "EUR"}},
        )

    async def fake_write_audit_log(*args, **kwargs):
        return None

    from app.ai import router as ai_router_module

    monkeypatch.setattr(ai_router_module, "handle_message", fake_handle_message)
    monkeypatch.setattr(ai_router_module, "_write_audit_log", fake_write_audit_log)
    client = _build_test_client()

    response = client.post("/ai/message", json={"message": "quel est mon solde ?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "answer"
    assert payload["message"] == "Votre solde disponible est de 245 EUR."
    assert payload["data"]["balance"] == 245


def test_ai_confirm_http_marks_non_transaction_pending_as_confirmed(monkeypatch):
    pending_action_id = uuid4()
    pending = SimpleNamespace(
        id=pending_action_id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        session_id=None,
        intent_code="wallet.balance",
        action_code="wallet.get_balance",
        payload={},
        confirmed_at=None,
    )

    async def fake_load_pending_action(db, *, pending_action_id, current_user):
        return pending

    from app.ai import router as ai_router_module

    monkeypatch.setattr(ai_router_module, "load_pending_action", fake_load_pending_action)
    client = _build_test_client()

    response = client.post(
        "/ai/confirm",
        json={"pending_action_id": str(pending_action_id), "confirm": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "confirmed"
    assert str(payload["pending_action_id"]) == str(pending_action_id)


def test_ai_internal_targeted_tests_endpoint_blocked_in_prod():
    original_env = settings.APP_ENV
    original_enabled = settings.AI_INTERNAL_TESTS_ENABLED
    settings.APP_ENV = "prod"
    settings.AI_INTERNAL_TESTS_ENABLED = True
    try:
        client = _build_test_client()
        response = client.post("/ai/internal/tests/targeted")
    finally:
        settings.APP_ENV = original_env
        settings.AI_INTERNAL_TESTS_ENABLED = original_enabled

    assert response.status_code == 404

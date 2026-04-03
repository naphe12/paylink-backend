from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import admin_required
from app.routers.admin.audit_search import router as audit_search_router


class _FakeResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    def __init__(self, *, total=0, rows=None, detail=None):
        self.total = total
        self.rows = rows or []
        self.detail = detail
        self.calls = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append({"sql": sql, "params": dict(params or {})})
        if "COUNT(*)" in sql:
            return _FakeResult(scalar_value=self.total)
        if "FROM paylink.audit_log a" in sql and "SELECT a.*" in sql:
            return _FakeResult(rows=[self.detail] if self.detail else [])
        return _FakeResult(rows=self.rows)


def _build_client(fake_db: _FakeDb) -> TestClient:
    app = FastAPI()
    app.include_router(audit_search_router)

    async def override_get_db():
        return fake_db

    async def override_admin_required():
        return SimpleNamespace(user_id=uuid4(), role="admin")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[admin_required] = override_admin_required
    return TestClient(app)


def test_admin_audit_search_returns_paginated_mixed_items():
    rows = [
        {
            "source": "step_up",
            "created_at": datetime(2026, 4, 3, 10, 45, tzinfo=timezone.utc),
            "event_type": "admin_step_up",
            "action": "ADMIN_STEP_UP_CHECK",
            "outcome": "verified",
            "actor_user_id": str(uuid4()),
            "actor_full_name": "Alice Admin",
            "actor_email": "alice@example.com",
            "actor_role": "admin",
            "target_type": "payment_intent",
            "target_id": "intent-42",
            "request_id": "req-42",
            "summary": "payment_manual_reconcile verified",
            "raw_ref": "101",
        },
        {
            "source": "audit",
            "created_at": datetime(2026, 4, 3, 9, 30, tzinfo=timezone.utc),
            "event_type": "audit_log",
            "action": "USER_LIMIT_UPDATED",
            "outcome": None,
            "actor_user_id": str(uuid4()),
            "actor_full_name": "Bob Operator",
            "actor_email": "bob@example.com",
            "actor_role": "operator",
            "target_type": "user",
            "target_id": str(uuid4()),
            "request_id": "",
            "summary": "USER_LIMIT_UPDATED user",
            "raw_ref": "99",
        },
    ]
    fake_db = _FakeDb(total=2, rows=rows)
    client = _build_client(fake_db)

    response = client.get(
        "/admin/audit/search?limit=25&offset=0&source=step_up&outcome=verified&action=ADMIN_STEP_UP_CHECK&role=admin&q=req-42"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["limit"] == 25
    assert payload["offset"] == 0
    assert payload["items"][0]["source"] == "step_up"
    assert payload["items"][0]["target_id"] == "intent-42"
    assert any(call["params"].get("source") == "step_up" for call in fake_db.calls)
    assert any(call["params"].get("outcome") == "verified" for call in fake_db.calls)
    assert any(call["params"].get("action") == "ADMIN_STEP_UP_CHECK" for call in fake_db.calls)
    assert any(call["params"].get("role") == "admin" for call in fake_db.calls)
    assert any(call["params"].get("search") == "%req-42%" for call in fake_db.calls)


def test_admin_audit_search_supports_target_and_request_id_filters():
    fake_db = _FakeDb(total=1, rows=[])
    client = _build_client(fake_db)

    response = client.get(
        "/admin/audit/search?target_id=trade-7&request_id=req-77&date_from=2026-04-01T00:00:00&date_to=2026-04-03T23:59:59"
    )

    assert response.status_code == 200
    assert any(call["params"].get("target_id") == "%trade-7%" for call in fake_db.calls)
    assert any(call["params"].get("request_id") == "%req-77%" for call in fake_db.calls)
    assert any("date_from" in call["params"] for call in fake_db.calls)
    assert any("date_to" in call["params"] for call in fake_db.calls)


def test_admin_audit_search_detail_returns_raw_payload():
    detail = {
        "id": 101,
        "created_at": datetime(2026, 4, 3, 10, 45, tzinfo=timezone.utc),
        "actor_user_id": str(uuid4()),
        "actor_role": "admin",
        "action": "ADMIN_STEP_UP_CHECK",
        "entity_type": "payment_intent",
        "entity_id": str(uuid4()),
        "before_state": None,
        "after_state": {"request_id": "req-42", "outcome": "verified"},
        "actor_full_name": "Alice Admin",
        "actor_email": "alice@example.com",
    }
    fake_db = _FakeDb(detail=detail)
    client = _build_client(fake_db)

    response = client.get("/admin/audit/search/step_up/101")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "step_up"
    assert payload["raw_ref"] == "101"
    assert payload["raw"]["action"] == "ADMIN_STEP_UP_CHECK"
    assert payload["raw"]["after_state"]["request_id"] == "req-42"

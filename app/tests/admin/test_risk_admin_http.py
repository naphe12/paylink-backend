from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import admin_required
from app.routers.admin.risk_admin import STEP_UP_EXPORT_HEADERS, router as risk_admin_router


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


class _FakeDb:
    def __init__(self, *, total=0, rows=None):
        self.total = total
        self.rows = rows or []
        self.calls = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append({"sql": sql, "params": dict(params or {})})
        if "COUNT(*)" in sql:
            return _FakeResult(scalar_value=self.total)
        return _FakeResult(rows=self.rows)


def _build_test_client(fake_db: _FakeDb) -> TestClient:
    app = FastAPI()
    app.include_router(risk_admin_router)

    async def override_get_db():
        return fake_db

    async def override_admin_required():
        return SimpleNamespace(user_id=uuid4(), role="admin", full_name="Admin Risk")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[admin_required] = override_admin_required
    return TestClient(app)


def test_get_admin_step_up_events_http_returns_paginated_items():
    row = {
        "id": 12,
        "created_at": datetime(2026, 4, 3, 10, 45, tzinfo=timezone.utc),
        "action": "ADMIN_STEP_UP_CHECK",
        "actor_user_id": str(uuid4()),
        "actor_role": "admin",
        "actor_full_name": "Alice Admin",
        "actor_email": "alice@example.com",
        "requested_action": "payment_manual_reconcile",
        "outcome": "verified",
        "request_id": "req-123",
        "target_type": "payment_intent",
        "target_id": str(uuid4()),
        "code": "admin_step_up_verified",
        "method": "token",
        "status_code": 200,
        "session_bound": True,
        "ip": "127.0.0.1",
        "user_agent": "pytest",
    }
    fake_db = _FakeDb(total=1, rows=[row])
    client = _build_test_client(fake_db)

    response = client.get(
        "/admin/risk/step-up-events?limit=20&offset=0&outcome=verified&requested_action=payment_manual_reconcile&q=alice"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert payload["items"][0]["actor_full_name"] == "Alice Admin"
    assert payload["items"][0]["requested_action"] == "payment_manual_reconcile"
    assert payload["items"][0]["outcome"] == "verified"
    assert any(call["params"].get("outcome") == "verified" for call in fake_db.calls)
    assert any(call["params"].get("requested_action") == "payment_manual_reconcile" for call in fake_db.calls)
    assert any(call["params"].get("search") == "%alice%" for call in fake_db.calls)


def test_export_admin_step_up_events_csv_http_uses_same_filters():
    row = {
        "created_at": "2026-04-03T10:45:00Z",
        "request_id": "req-456",
        "action": "ADMIN_STEP_UP_ISSUED",
        "outcome": "issued",
        "requested_action": "escrow_refund_request",
        "target_type": "escrow_order",
        "target_id": str(uuid4()),
        "code": "",
        "method": "token",
        "status_code": 200,
        "session_bound": True,
        "actor_user_id": str(uuid4()),
        "actor_full_name": "Bob Admin",
        "actor_email": "bob@example.com",
        "actor_role": "admin",
        "ip": "127.0.0.1",
        "user_agent": "pytest",
    }
    fake_db = _FakeDb(total=1, rows=[row])
    client = _build_test_client(fake_db)

    response = client.get(
        "/admin/risk/step-up-events/export.csv?outcome=issued&requested_action=escrow_refund_request&q=bob"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "admin_step_up_events.csv" in response.headers["content-disposition"]
    body = response.text
    assert ",".join(STEP_UP_EXPORT_HEADERS) in body
    assert "Bob Admin" in body
    assert "escrow_refund_request" in body
    assert any(call["params"].get("outcome") == "issued" for call in fake_db.calls)
    assert any(call["params"].get("requested_action") == "escrow_refund_request" for call in fake_db.calls)
    assert any(call["params"].get("search") == "%bob%" for call in fake_db.calls)


def test_get_admin_step_up_summary_http_returns_denied_codes():
    class _SummaryDb(_FakeDb):
        async def execute(self, statement, params=None):
            sql = str(statement)
            self.calls.append({"sql": sql, "params": dict(params or {})})
            if "COUNT(*)::int AS total" in sql:
                return _FakeResult(
                    rows=[
                        {
                            "total": 12,
                            "issued": 4,
                            "verified": 3,
                            "denied": 4,
                            "required": 1,
                        }
                    ]
                )
            if "GROUP BY COALESCE(a.after_state->>'code', 'unknown')" in sql:
                return _FakeResult(rows=[{"code": "admin_step_up_session_mismatch", "count": 2}])
            if "GROUP BY COALESCE(a.after_state->>'requested_action', '*')" in sql:
                return _FakeResult(
                    rows=[
                        {
                            "requested_action": "payment_manual_reconcile",
                            "total": 5,
                            "denied": 2,
                            "verified": 2,
                            "required": 1,
                        }
                    ]
                )
            raise AssertionError(f"Unexpected SQL: {sql}")

    client = _build_test_client(_SummaryDb())
    response = client.get("/admin/risk/step-up-summary?window_hours=24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["denied"] == 4
    assert payload["denied_codes"][0]["code"] == "admin_step_up_session_mismatch"
    assert payload["by_action"][0]["requested_action"] == "payment_manual_reconcile"

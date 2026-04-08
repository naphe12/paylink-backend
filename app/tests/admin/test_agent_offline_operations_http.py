from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_agent
from app.routers.admin.agent_offline_operations import router as admin_agent_offline_router
from app.routers.agent.offline_operations import router as agent_offline_router


class _FakeDb:
    pass


def _operation_payload(*, operation_id: str, agent_user_id: str, agent_id: str, client_user_id: str, status: str, admin: bool = False):
    payload = {
        "operation_id": operation_id,
        "agent_user_id": agent_user_id,
        "agent_id": agent_id,
        "client_user_id": client_user_id,
        "client_label": "Client Offline",
        "operation_type": "cash_out",
        "amount": "25000.00",
        "currency_code": "BIF",
        "note": "zone sans reseau",
        "offline_reference": "off_ref_1",
        "status": status,
        "failure_reason": "Solde insuffisant pour effectuer ce retrait" if status == "failed" else None,
        "conflict_reason": "insufficient_funds" if status in {"failed", "synced"} else None,
        "conflict_reason_label": "Le client n'a plus assez de solde au moment de la sync" if status in {"failed", "synced"} else None,
        "requires_review": status in {"failed", "synced"},
        "is_stale": status == "failed",
        "queued_age_minutes": 220,
        "snapshot_available": "50000.00",
        "current_available": "12000.00",
        "balance_delta": "-38000.00",
        "synced_response": {"message": "Cash-out synchronise", "new_balance": 5000} if status == "synced" else None,
        "metadata": {},
        "queued_at": "2026-04-06T08:00:00Z",
        "synced_at": "2026-04-06T08:10:00Z" if status == "synced" else None,
        "created_at": "2026-04-06T08:00:00Z",
        "updated_at": "2026-04-06T08:10:00Z" if status == "synced" else "2026-04-06T08:05:00Z",
    }
    if admin:
        payload.update(
            {
                "agent_label": "Agent Marie",
                "agent_email": "marie@pesapaid.com",
                "agent_phone_e164": "+25770000001",
                "client_email": "client@pesapaid.com",
                "client_phone_e164": "+25770000002",
                "client_paytag": "@client",
            }
        )
    return payload


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(agent_offline_router)
    app.include_router(admin_agent_offline_router)
    db = _FakeDb()
    current_agent = SimpleNamespace(user_id=uuid4(), role="agent", email="agent@example.com")
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")

    async def override_get_db():
        return db

    async def override_get_current_agent():
        return current_agent

    async def override_get_current_admin():
        return current_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_agent] = override_get_current_agent
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_agent_offline_routes_create_list_sync_batch_and_cancel(monkeypatch):
    from app.routers.agent import offline_operations as agent_module

    operation_id = str(uuid4())
    agent_user_id = str(uuid4())
    agent_id = str(uuid4())
    client_user_id = str(uuid4())

    async def fake_list_agent_offline_operations(db, *, current_agent, status=None):
        assert status == "queued"
        return [_operation_payload(operation_id=operation_id, agent_user_id=agent_user_id, agent_id=agent_id, client_user_id=client_user_id, status="queued")]

    async def fake_create_agent_offline_operation(db, *, current_agent, payload):
        assert str(payload.client_user_id) == client_user_id
        assert payload.operation_type == "cash_out"
        return _operation_payload(operation_id=operation_id, agent_user_id=agent_user_id, agent_id=agent_id, client_user_id=client_user_id, status="queued")

    async def fake_sync_agent_offline_operation(db, *, current_agent, operation_id, force=False):
        assert force is False
        return _operation_payload(operation_id=str(operation_id), agent_user_id=agent_user_id, agent_id=agent_id, client_user_id=client_user_id, status="synced")

    async def fake_sync_pending_agent_offline_operations(db, *, current_agent, force=False):
        assert force is False
        return {
            "synced": 1,
            "failed": 0,
            "skipped": 0,
            "operations": [
                _operation_payload(operation_id=operation_id, agent_user_id=agent_user_id, agent_id=agent_id, client_user_id=client_user_id, status="synced")
            ],
        }

    async def fake_cancel_agent_offline_operation(db, *, current_agent, operation_id):
        return _operation_payload(operation_id=str(operation_id), agent_user_id=agent_user_id, agent_id=agent_id, client_user_id=client_user_id, status="cancelled")

    monkeypatch.setattr(agent_module, "list_agent_offline_operations", fake_list_agent_offline_operations)
    monkeypatch.setattr(agent_module, "create_agent_offline_operation", fake_create_agent_offline_operation)
    monkeypatch.setattr(agent_module, "sync_agent_offline_operation", fake_sync_agent_offline_operation)
    monkeypatch.setattr(agent_module, "sync_pending_agent_offline_operations", fake_sync_pending_agent_offline_operations)
    monkeypatch.setattr(agent_module, "cancel_agent_offline_operation", fake_cancel_agent_offline_operation)

    client = _build_test_client()

    list_response = client.get("/agent/offline-operations?status=queued")
    assert list_response.status_code == 200
    assert list_response.json()[0]["requires_review"] is False

    create_response = client.post(
        "/agent/offline-operations",
        json={"client_user_id": client_user_id, "operation_type": "cash_out", "amount": 25000, "note": "zone sans reseau"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["offline_reference"] == "off_ref_1"

    sync_response = client.post(f"/agent/offline-operations/{operation_id}/sync")
    assert sync_response.status_code == 200
    assert sync_response.json()["status"] == "synced"
    assert sync_response.json()["requires_review"] is True

    batch_response = client.post("/agent/offline-operations/sync-pending")
    assert batch_response.status_code == 200
    assert batch_response.json()["synced"] == 1

    cancel_response = client.post(f"/agent/offline-operations/{operation_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_admin_agent_offline_routes_list_detail_retry_and_cancel(monkeypatch):
    from app.routers.admin import agent_offline_operations as admin_module

    operation_id = str(uuid4())
    agent_user_id = str(uuid4())
    agent_id = str(uuid4())
    client_user_id = str(uuid4())

    async def fake_list_admin_agent_offline_operations(db, *, status=None, q=None, limit=200):
        assert status == "failed"
        assert q == "Client Offline"
        assert limit == 50
        return [
            _operation_payload(
                operation_id=operation_id,
                agent_user_id=agent_user_id,
                agent_id=agent_id,
                client_user_id=client_user_id,
                status="failed",
                admin=True,
            )
        ]

    async def fake_get_admin_agent_offline_operation_detail(db, *, operation_id):
        return _operation_payload(
            operation_id=str(operation_id),
            agent_user_id=agent_user_id,
            agent_id=agent_id,
            client_user_id=client_user_id,
            status="failed",
            admin=True,
        )

    async def fake_retry_admin_agent_offline_operation(db, *, operation_id, force=False):
        assert force is False
        return _operation_payload(
            operation_id=str(operation_id),
            agent_user_id=agent_user_id,
            agent_id=agent_id,
            client_user_id=client_user_id,
            status="synced",
            admin=True,
        )

    async def fake_cancel_admin_agent_offline_operation(db, *, operation_id):
        return _operation_payload(
            operation_id=str(operation_id),
            agent_user_id=agent_user_id,
            agent_id=agent_id,
            client_user_id=client_user_id,
            status="cancelled",
            admin=True,
        )

    monkeypatch.setattr(admin_module, "list_admin_agent_offline_operations", fake_list_admin_agent_offline_operations)
    monkeypatch.setattr(admin_module, "get_admin_agent_offline_operation_detail", fake_get_admin_agent_offline_operation_detail)
    monkeypatch.setattr(admin_module, "retry_admin_agent_offline_operation", fake_retry_admin_agent_offline_operation)
    monkeypatch.setattr(admin_module, "cancel_admin_agent_offline_operation", fake_cancel_admin_agent_offline_operation)

    client = _build_test_client()

    list_response = client.get("/admin/agent/offline-operations?status=failed&q=Client%20Offline&limit=50")
    assert list_response.status_code == 200
    assert list_response.json()[0]["agent_label"] == "Agent Marie"

    detail_response = client.get(f"/admin/agent/offline-operations/{operation_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["conflict_reason"] == "insufficient_funds"

    retry_response = client.post(f"/admin/agent/offline-operations/{operation_id}/retry")
    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == "synced"

    cancel_response = client.post(f"/admin/agent/offline-operations/{operation_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_offline_routes_accept_force_payload(monkeypatch):
    from app.routers.agent import offline_operations as agent_module
    from app.routers.admin import agent_offline_operations as admin_module

    operation_id = str(uuid4())
    agent_user_id = str(uuid4())
    agent_id = str(uuid4())
    client_user_id = str(uuid4())
    calls = {"sync_one": None, "sync_batch": None, "retry": None}

    async def fake_sync_agent_offline_operation(db, *, current_agent, operation_id, force=False):
        calls["sync_one"] = force
        return _operation_payload(
            operation_id=str(operation_id),
            agent_user_id=agent_user_id,
            agent_id=agent_id,
            client_user_id=client_user_id,
            status="synced",
        )

    async def fake_sync_pending_agent_offline_operations(db, *, current_agent, force=False):
        calls["sync_batch"] = force
        return {
            "synced": 1,
            "failed": 0,
            "skipped": 0,
            "operations": [
                _operation_payload(
                    operation_id=operation_id,
                    agent_user_id=agent_user_id,
                    agent_id=agent_id,
                    client_user_id=client_user_id,
                    status="synced",
                )
            ],
        }

    async def fake_retry_admin_agent_offline_operation(db, *, operation_id, force=False):
        calls["retry"] = force
        return _operation_payload(
            operation_id=str(operation_id),
            agent_user_id=agent_user_id,
            agent_id=agent_id,
            client_user_id=client_user_id,
            status="synced",
            admin=True,
        )

    monkeypatch.setattr(agent_module, "sync_agent_offline_operation", fake_sync_agent_offline_operation)
    monkeypatch.setattr(agent_module, "sync_pending_agent_offline_operations", fake_sync_pending_agent_offline_operations)
    monkeypatch.setattr(admin_module, "retry_admin_agent_offline_operation", fake_retry_admin_agent_offline_operation)

    client = _build_test_client()

    sync_one_response = client.post(f"/agent/offline-operations/{operation_id}/sync", json={"force": True})
    assert sync_one_response.status_code == 200
    assert calls["sync_one"] is True

    sync_batch_response = client.post("/agent/offline-operations/sync-pending", json={"force": True})
    assert sync_batch_response.status_code == 200
    assert calls["sync_batch"] is True

    retry_response = client.post(f"/admin/agent/offline-operations/{operation_id}/retry", json={"force": True})
    assert retry_response.status_code == 200
    assert calls["retry"] is True

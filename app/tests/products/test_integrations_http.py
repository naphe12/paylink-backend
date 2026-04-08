from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_agent, get_current_user_db
from app.routers.agent.offline_operations import router as agent_offline_router
from app.routers.merchant_api import router as merchant_api_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(merchant_api_router)
    app.include_router(agent_offline_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@owner")
    current_agent = SimpleNamespace(
        user_id=uuid4(),
        agent_id=uuid4(),
        role="agent",
        email="agent@example.com",
        paytag="@agent",
    )

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    async def override_get_current_agent():
        return current_agent

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    app.dependency_overrides[get_current_agent] = override_get_current_agent
    return TestClient(app)


def _api_key_payload(key_id, business_id, **overrides):
    payload = {
        "key_id": str(key_id),
        "business_id": str(business_id),
        "key_name": "Production key",
        "key_prefix": "pk_live_123",
        "is_active": True,
        "last_used_at": None,
        "revoked_at": None,
        "metadata": {},
        "created_at": "2026-04-06T10:00:00Z",
        "updated_at": "2026-04-06T10:00:00Z",
        "plain_api_key": "pp_live_secret",
    }
    payload.update(overrides)
    return payload


def _webhook_payload(webhook_id, business_id, **overrides):
    payload = {
        "webhook_id": str(webhook_id),
        "business_id": str(business_id),
        "target_url": "https://merchant.example.com/webhooks/payments",
        "status": "active",
        "event_types": ["payment_request.paid"],
        "is_active": True,
        "last_tested_at": None,
        "revoked_at": None,
        "metadata": {},
        "created_at": "2026-04-06T10:00:00Z",
        "updated_at": "2026-04-06T10:00:00Z",
        "plain_signing_secret": "whsec_test",
    }
    payload.update(overrides)
    return payload


def _event_payload(event_id, webhook_id, business_id, **overrides):
    payload = {
        "event_id": str(event_id),
        "webhook_id": str(webhook_id),
        "business_id": str(business_id),
        "event_type": "payment_request.paid",
        "delivery_status": "queued",
        "response_status_code": None,
        "request_signature": "sig_test",
        "payload": {"request_id": str(uuid4())},
        "response_body": None,
        "attempt_count": 0,
        "last_attempted_at": None,
        "next_retry_at": "2026-04-06T10:05:00Z",
        "delivered_at": None,
        "metadata": {},
        "created_at": "2026-04-06T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def _offline_operation_payload(operation_id, agent_user_id, agent_id, client_user_id, **overrides):
    payload = {
        "operation_id": str(operation_id),
        "agent_user_id": str(agent_user_id),
        "agent_id": str(agent_id),
        "client_user_id": str(client_user_id),
        "client_label": "@client",
        "operation_type": "cash_in",
        "amount": "15000.00",
        "currency_code": "BIF",
        "note": "Terrain",
        "offline_reference": "off_ref_1",
        "status": "queued",
        "failure_reason": None,
        "conflict_reason": None,
        "conflict_reason_label": None,
        "requires_review": False,
        "is_stale": False,
        "queued_age_minutes": 5,
        "snapshot_available": "50000.00",
        "current_available": "50000.00",
        "balance_delta": "0.00",
        "synced_response": None,
        "metadata": {},
        "queued_at": "2026-04-06T10:00:00Z",
        "synced_at": None,
        "created_at": "2026-04-06T10:00:00Z",
        "updated_at": "2026-04-06T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_merchant_api_routes(monkeypatch):
    from app.routers import merchant_api as merchant_module

    business_id = uuid4()
    key_id = uuid4()
    webhook_id = uuid4()
    event_id = uuid4()

    async def fake_list_business_integrations(db, *, business_id, current_user):
        return {
            "business_id": str(business_id),
            "business_label": "Alpha Shop",
            "membership_role": "owner",
            "api_keys": [_api_key_payload(key_id, business_id)],
            "webhooks": [_webhook_payload(webhook_id, business_id)],
            "recent_events": [_event_payload(event_id, webhook_id, business_id)],
        }

    async def fake_create_business_api_key(db, *, business_id, current_user, payload):
        assert payload.key_name == "Production key"
        return _api_key_payload(key_id, business_id)

    async def fake_revoke_business_api_key(db, *, key_id, current_user):
        return _api_key_payload(key_id, business_id, is_active=False, revoked_at="2026-04-06T10:20:00Z", plain_api_key=None)

    async def fake_create_business_webhook(db, *, business_id, current_user, payload):
        assert str(payload.target_url) == "https://merchant.example.com/webhooks/payments"
        return _webhook_payload(webhook_id, business_id)

    async def fake_update_business_webhook_status(db, *, webhook_id, current_user, payload):
        assert payload.status == "paused"
        return _webhook_payload(webhook_id, business_id, status="paused", is_active=False, plain_signing_secret=None)

    async def fake_rotate_webhook_secret(db, *, webhook_id, current_user):
        return _webhook_payload(webhook_id, business_id, plain_signing_secret="whsec_rotated")

    async def fake_send_test_webhook(db, *, webhook_id, current_user):
        return _event_payload(event_id, webhook_id, business_id, delivery_status="sent", attempt_count=1)

    async def fake_retry_webhook_event(db, *, event_id, current_user):
        return _event_payload(event_id, webhook_id, business_id, delivery_status="retrying", attempt_count=2)

    async def fake_retry_due_webhook_events(db, *, business_id, current_user):
        return [_event_payload(event_id, webhook_id, business_id, delivery_status="retrying", attempt_count=2)]

    monkeypatch.setattr(merchant_module, "list_business_integrations", fake_list_business_integrations)
    monkeypatch.setattr(merchant_module, "create_business_api_key", fake_create_business_api_key)
    monkeypatch.setattr(merchant_module, "revoke_business_api_key", fake_revoke_business_api_key)
    monkeypatch.setattr(merchant_module, "create_business_webhook", fake_create_business_webhook)
    monkeypatch.setattr(merchant_module, "update_business_webhook_status", fake_update_business_webhook_status)
    monkeypatch.setattr(merchant_module, "rotate_webhook_secret", fake_rotate_webhook_secret)
    monkeypatch.setattr(merchant_module, "send_test_webhook", fake_send_test_webhook)
    monkeypatch.setattr(merchant_module, "retry_webhook_event", fake_retry_webhook_event)
    monkeypatch.setattr(merchant_module, "retry_due_webhook_events", fake_retry_due_webhook_events)

    client = _build_test_client()

    integrations_response = client.get(f"/merchant-api/businesses/{business_id}")
    assert integrations_response.status_code == 200
    assert integrations_response.json()["business_label"] == "Alpha Shop"

    key_response = client.post(f"/merchant-api/businesses/{business_id}/keys", json={"key_name": "Production key"})
    assert key_response.status_code == 200
    assert key_response.json()["plain_api_key"] == "pp_live_secret"

    revoke_response = client.post(f"/merchant-api/keys/{key_id}/revoke")
    assert revoke_response.status_code == 200
    assert revoke_response.json()["is_active"] is False

    webhook_response = client.post(
        f"/merchant-api/businesses/{business_id}/webhooks",
        json={"target_url": "https://merchant.example.com/webhooks/payments", "event_types": ["payment_request.paid"]},
    )
    assert webhook_response.status_code == 200
    assert webhook_response.json()["plain_signing_secret"] == "whsec_test"

    webhook_status_response = client.post(f"/merchant-api/webhooks/{webhook_id}/status", json={"status": "paused"})
    assert webhook_status_response.status_code == 200
    assert webhook_status_response.json()["status"] == "paused"

    rotate_secret_response = client.post(f"/merchant-api/webhooks/{webhook_id}/rotate-secret")
    assert rotate_secret_response.status_code == 200
    assert rotate_secret_response.json()["plain_signing_secret"] == "whsec_rotated"

    test_webhook_response = client.post(f"/merchant-api/webhooks/{webhook_id}/test")
    assert test_webhook_response.status_code == 200
    assert test_webhook_response.json()["delivery_status"] == "sent"

    retry_event_response = client.post(f"/merchant-api/webhook-events/{event_id}/retry")
    assert retry_event_response.status_code == 200
    assert retry_event_response.json()["attempt_count"] == 2

    retry_due_response = client.post(f"/merchant-api/businesses/{business_id}/webhooks/retry-due")
    assert retry_due_response.status_code == 200
    assert retry_due_response.json()[0]["delivery_status"] == "retrying"


def test_agent_offline_routes(monkeypatch):
    from app.routers.agent import offline_operations as agent_offline_module

    client_user_id = uuid4()
    operation_id = uuid4()

    async def fake_list_agent_offline_operations(db, *, current_agent, status=None):
        assert status == "queued"
        return [
            _offline_operation_payload(
                operation_id,
                current_agent.user_id,
                current_agent.agent_id,
                client_user_id,
            )
        ]

    async def fake_create_agent_offline_operation(db, *, current_agent, payload):
        assert payload.operation_type == "cash_in"
        return _offline_operation_payload(operation_id, current_agent.user_id, current_agent.agent_id, payload.client_user_id)

    async def fake_sync_pending_agent_offline_operations(db, *, current_agent, force=False):
        assert force is False
        return {
            "synced": 1,
            "failed": 0,
            "skipped": 0,
            "operations": [
                _offline_operation_payload(
                    operation_id,
                    current_agent.user_id,
                    current_agent.agent_id,
                    client_user_id,
                    status="synced",
                    synced_at="2026-04-06T10:20:00Z",
                    synced_response={"status": "ok"},
                )
            ],
        }

    async def fake_sync_agent_offline_operation(db, *, current_agent, operation_id, force=False):
        assert force is False
        return _offline_operation_payload(
            operation_id,
            current_agent.user_id,
            current_agent.agent_id,
            client_user_id,
            status="synced",
            synced_at="2026-04-06T10:20:00Z",
            synced_response={"status": "ok"},
        )

    async def fake_cancel_agent_offline_operation(db, *, current_agent, operation_id):
        return _offline_operation_payload(
            operation_id,
            current_agent.user_id,
            current_agent.agent_id,
            client_user_id,
            status="cancelled",
        )

    monkeypatch.setattr(agent_offline_module, "list_agent_offline_operations", fake_list_agent_offline_operations)
    monkeypatch.setattr(agent_offline_module, "create_agent_offline_operation", fake_create_agent_offline_operation)
    monkeypatch.setattr(agent_offline_module, "sync_pending_agent_offline_operations", fake_sync_pending_agent_offline_operations)
    monkeypatch.setattr(agent_offline_module, "sync_agent_offline_operation", fake_sync_agent_offline_operation)
    monkeypatch.setattr(agent_offline_module, "cancel_agent_offline_operation", fake_cancel_agent_offline_operation)

    client = _build_test_client()

    list_response = client.get("/agent/offline-operations?status=queued")
    assert list_response.status_code == 200
    assert list_response.json()[0]["offline_reference"] == "off_ref_1"

    create_response = client.post(
        "/agent/offline-operations",
        json={"client_user_id": str(client_user_id), "operation_type": "cash_in", "amount": 15000, "note": "Terrain"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["operation_type"] == "cash_in"

    sync_pending_response = client.post("/agent/offline-operations/sync-pending")
    assert sync_pending_response.status_code == 200
    assert sync_pending_response.json()["synced"] == 1

    sync_one_response = client.post(f"/agent/offline-operations/{operation_id}/sync")
    assert sync_one_response.status_code == 200
    assert sync_one_response.json()["status"] == "synced"

    cancel_response = client.post(f"/agent/offline-operations/{operation_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

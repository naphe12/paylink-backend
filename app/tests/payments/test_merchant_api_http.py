from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.merchant_api import router as merchant_api_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(merchant_api_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@client")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def test_merchant_api_routes_cover_key_webhook_and_retry(monkeypatch):
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
            "api_keys": [
                {
                    "key_id": str(key_id),
                    "business_id": str(business_id),
                    "key_name": "Serveur prod",
                    "key_prefix": "pk_live_alpha",
                    "is_active": True,
                    "last_used_at": None,
                    "revoked_at": None,
                    "metadata": {"last4": "9z9z"},
                    "created_at": "2026-04-06T10:00:00Z",
                    "updated_at": "2026-04-06T10:00:00Z",
                    "plain_api_key": None,
                }
            ],
            "webhooks": [
                {
                    "webhook_id": str(webhook_id),
                    "business_id": str(business_id),
                    "target_url": "https://merchant.example.com/webhook",
                    "status": "active",
                    "event_types": ["payment.request.paid"],
                    "is_active": True,
                    "last_tested_at": "2026-04-06T10:00:00Z",
                    "revoked_at": None,
                    "metadata": {"last4": "abcd"},
                    "created_at": "2026-04-06T10:00:00Z",
                    "updated_at": "2026-04-06T10:00:00Z",
                    "plain_signing_secret": None,
                }
            ],
            "recent_events": [
                {
                    "event_id": str(event_id),
                    "webhook_id": str(webhook_id),
                    "business_id": str(business_id),
                    "event_type": "merchant.webhook.test",
                    "delivery_status": "failed",
                    "response_status_code": 503,
                    "request_signature": "abc123",
                    "payload": {"event": "merchant.webhook.test"},
                    "response_body": "Upstream unavailable",
                    "attempt_count": 1,
                    "last_attempted_at": "2026-04-06T10:00:00Z",
                    "next_retry_at": "2026-04-06T10:05:00Z",
                    "delivered_at": None,
                    "metadata": {"mode": "test"},
                    "created_at": "2026-04-06T10:00:00Z",
                }
            ],
        }

    async def fake_create_business_api_key(db, *, business_id, current_user, payload):
        assert payload.key_name == "Serveur prod"
        return {
            "key_id": str(key_id),
            "business_id": str(business_id),
            "key_name": payload.key_name,
            "key_prefix": "pk_live_alpha",
            "is_active": True,
            "last_used_at": None,
            "revoked_at": None,
            "metadata": {"last4": "9z9z"},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "plain_api_key": "pk_live_secret",
        }

    async def fake_revoke_business_api_key(db, *, key_id, current_user):
        return {
            "key_id": str(key_id),
            "business_id": str(business_id),
            "key_name": "Serveur prod",
            "key_prefix": "pk_live_alpha",
            "is_active": False,
            "last_used_at": None,
            "revoked_at": "2026-04-06T10:03:00Z",
            "metadata": {"last4": "9z9z"},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:03:00Z",
            "plain_api_key": None,
        }

    async def fake_create_business_webhook(db, *, business_id, current_user, payload):
        assert str(payload.target_url) == "https://merchant.example.com/webhook"
        assert payload.max_consecutive_failures == 4
        return {
            "webhook_id": str(webhook_id),
            "business_id": str(business_id),
            "target_url": str(payload.target_url),
            "status": "active",
            "event_types": payload.event_types,
            "is_active": True,
            "last_tested_at": None,
            "revoked_at": None,
            "metadata": {"last4": "abcd"},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "plain_signing_secret": "whsec_secret",
        }

    async def fake_update_business_webhook_status(db, *, webhook_id, current_user, payload):
        assert payload.status == "paused"
        return {
            "webhook_id": str(webhook_id),
            "business_id": str(business_id),
            "target_url": "https://merchant.example.com/webhook",
            "status": "paused",
            "event_types": ["payment.request.paid"],
            "is_active": False,
            "last_tested_at": None,
            "revoked_at": None,
            "metadata": {"last4": "abcd"},
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:02:00Z",
            "plain_signing_secret": None,
        }

    async def fake_send_test_webhook(db, *, webhook_id, current_user):
        return {
            "event_id": str(event_id),
            "webhook_id": str(webhook_id),
            "business_id": str(business_id),
            "event_type": "merchant.webhook.test",
            "delivery_status": "failed",
            "response_status_code": 503,
            "request_signature": "abc123",
            "payload": {"event": "merchant.webhook.test"},
            "response_body": "Upstream unavailable",
            "attempt_count": 1,
            "last_attempted_at": "2026-04-06T10:00:00Z",
            "next_retry_at": "2026-04-06T10:05:00Z",
            "delivered_at": None,
            "metadata": {"mode": "test"},
            "created_at": "2026-04-06T10:00:00Z",
        }

    async def fake_retry_webhook_event(db, *, event_id, current_user):
        return {
            "event_id": str(event_id),
            "webhook_id": str(webhook_id),
            "business_id": str(business_id),
            "event_type": "merchant.webhook.test",
            "delivery_status": "delivered",
            "response_status_code": 200,
            "request_signature": "abc123",
            "payload": {"event": "merchant.webhook.test"},
            "response_body": "ok",
            "attempt_count": 2,
            "last_attempted_at": "2026-04-06T10:06:00Z",
            "next_retry_at": None,
            "delivered_at": "2026-04-06T10:06:00Z",
            "metadata": {"mode": "manual_retry"},
            "created_at": "2026-04-06T10:00:00Z",
        }

    async def fake_retry_due_webhook_events(db, *, business_id, current_user):
        return [
            {
                "event_id": str(event_id),
                "webhook_id": str(webhook_id),
                "business_id": str(business_id),
                "event_type": "merchant.webhook.test",
                "delivery_status": "delivered",
                "response_status_code": 200,
                "request_signature": "abc123",
                "payload": {"event": "merchant.webhook.test"},
                "response_body": "ok",
                "attempt_count": 2,
                "last_attempted_at": "2026-04-06T10:06:00Z",
                "next_retry_at": None,
                "delivered_at": "2026-04-06T10:06:00Z",
                "metadata": {"mode": "scheduled_retry"},
                "created_at": "2026-04-06T10:00:00Z",
            }
        ]

    monkeypatch.setattr(merchant_module, "list_business_integrations", fake_list_business_integrations)
    monkeypatch.setattr(merchant_module, "create_business_api_key", fake_create_business_api_key)
    monkeypatch.setattr(merchant_module, "revoke_business_api_key", fake_revoke_business_api_key)
    monkeypatch.setattr(merchant_module, "create_business_webhook", fake_create_business_webhook)
    monkeypatch.setattr(merchant_module, "update_business_webhook_status", fake_update_business_webhook_status)
    monkeypatch.setattr(merchant_module, "send_test_webhook", fake_send_test_webhook)
    monkeypatch.setattr(merchant_module, "retry_webhook_event", fake_retry_webhook_event)
    monkeypatch.setattr(merchant_module, "retry_due_webhook_events", fake_retry_due_webhook_events)

    client = _build_test_client()

    list_response = client.get(f"/merchant-api/businesses/{business_id}")
    assert list_response.status_code == 200
    assert list_response.json()["business_label"] == "Alpha Shop"

    create_key_response = client.post(
        f"/merchant-api/businesses/{business_id}/keys",
        json={"key_name": "Serveur prod"},
    )
    assert create_key_response.status_code == 200
    assert create_key_response.json()["plain_api_key"] == "pk_live_secret"

    revoke_key_response = client.post(f"/merchant-api/keys/{key_id}/revoke")
    assert revoke_key_response.status_code == 200
    assert revoke_key_response.json()["is_active"] is False

    create_webhook_response = client.post(
        f"/merchant-api/businesses/{business_id}/webhooks",
        json={
            "target_url": "https://merchant.example.com/webhook",
            "event_types": ["payment.request.paid"],
            "max_consecutive_failures": 4,
        },
    )
    assert create_webhook_response.status_code == 200
    assert create_webhook_response.json()["plain_signing_secret"] == "whsec_secret"

    update_webhook_response = client.post(
        f"/merchant-api/webhooks/{webhook_id}/status",
        json={"status": "paused"},
    )
    assert update_webhook_response.status_code == 200
    assert update_webhook_response.json()["status"] == "paused"

    test_response = client.post(f"/merchant-api/webhooks/{webhook_id}/test")
    assert test_response.status_code == 200
    assert test_response.json()["delivery_status"] == "failed"

    retry_response = client.post(f"/merchant-api/webhook-events/{event_id}/retry")
    assert retry_response.status_code == 200
    assert retry_response.json()["delivery_status"] == "delivered"

    retry_due_response = client.post(f"/merchant-api/businesses/{business_id}/webhooks/retry-due")
    assert retry_due_response.status_code == 200
    assert retry_due_response.json()[0]["metadata"]["mode"] == "scheduled_retry"

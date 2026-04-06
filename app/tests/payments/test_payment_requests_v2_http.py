from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.dependencies.auth import get_current_admin
from app.routers.admin.payment_requests import router as admin_payment_requests_router
from app.routers.wallet.payment_requests_v2 import router as wallet_payment_requests_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(wallet_payment_requests_router)
    app.include_router(admin_payment_requests_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@client")
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com", paytag="@admin")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    async def override_get_current_admin():
        return current_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_wallet_payment_requests_list_and_detail(monkeypatch):
    from app.routers.wallet import payment_requests_v2 as wallet_module

    current_user_id = uuid4()
    request_id = uuid4()

    async def fake_list_payment_requests(db, *, current_user, status=None):
        assert status == "pending"
        return [
            {
                "request_id": str(request_id),
                "requester_user_id": str(current_user_id),
                "payer_user_id": None,
                "amount": "125.00",
                "currency_code": "EUR",
                "status": "pending",
                "channel": "direct",
                "title": "Loyer",
                "note": "Avril",
                "share_token": "PR-ABC",
                "due_at": None,
                "expires_at": None,
                "paid_at": None,
                "declined_at": None,
                "cancelled_at": None,
                "last_reminder_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "counterpart_label": "@payer",
                "role": "requester",
            }
        ]

    async def fake_get_payment_request_detail(db, *, request_id, current_user):
        return {
            "request": {
                "request_id": str(request_id),
                "requester_user_id": str(current_user_id),
                "payer_user_id": None,
                "amount": "125.00",
                "currency_code": "EUR",
                "status": "pending",
                "channel": "direct",
                "title": "Loyer",
                "note": "Avril",
                "share_token": "PR-ABC",
                "due_at": None,
                "expires_at": None,
                "paid_at": None,
                "declined_at": None,
                "cancelled_at": None,
                "last_reminder_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "counterpart_label": "@payer",
                "role": "requester",
            },
            "events": [
                {
                    "event_id": str(uuid4()),
                    "actor_user_id": None,
                    "actor_role": "client",
                    "event_type": "created",
                    "before_status": None,
                    "after_status": "pending",
                    "metadata": {},
                    "created_at": "2026-04-05T10:00:00Z",
                }
            ],
        }

    monkeypatch.setattr(wallet_module, "list_payment_requests", fake_list_payment_requests)
    monkeypatch.setattr(wallet_module, "get_payment_request_detail", fake_get_payment_request_detail)

    client = _build_test_client()

    response = client.get("/wallet/payment-requests?status=pending")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "Loyer"
    assert payload[0]["status"] == "pending"

    detail_response = client.get(f"/wallet/payment-requests/{request_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["request"]["share_token"] == "PR-ABC"
    assert detail["events"][0]["event_type"] == "created"


def test_wallet_payment_request_actions(monkeypatch):
    from app.routers.wallet import payment_requests_v2 as wallet_module

    request_id = uuid4()

    async def fake_list_payment_requests(db, *, current_user, status=None):
        return [
            {
                "request_id": str(request_id),
                "requester_user_id": str(uuid4()),
                "payer_user_id": str(current_user.user_id),
                "amount": "50.00",
                "currency_code": "EUR",
                "status": "paid",
                "channel": "direct",
                "title": "Facture",
                "note": None,
                "share_token": "PR-ACT",
                "due_at": None,
                "expires_at": None,
                "paid_at": "2026-04-05T12:00:00Z",
                "declined_at": None,
                "cancelled_at": None,
                "last_reminder_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T12:00:00Z",
                "counterpart_label": "@sender",
                "role": "payer",
            }
        ]

    async def fake_pay_payment_request(db, *, request_id, current_user, reason=None):
        return SimpleNamespace(request_id=request_id)

    monkeypatch.setattr(wallet_module, "list_payment_requests", fake_list_payment_requests)
    monkeypatch.setattr(wallet_module, "pay_payment_request", fake_pay_payment_request)

    client = _build_test_client()
    response = client.post(f"/wallet/payment-requests/{request_id}/pay", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == str(request_id)
    assert payload["status"] == "paid"


def test_admin_payment_requests_v2_list_and_detail(monkeypatch):
    from app.routers.admin import payment_requests as admin_module

    request_id = uuid4()

    async def fake_list_admin_payment_requests_v2(db, *, status=None, q=None, limit=200):
        assert status == "pending"
        assert q == "loyer"
        assert limit == 50
        return [
            {
                "request_id": str(request_id),
                "requester_user_id": str(uuid4()),
                "payer_user_id": str(uuid4()),
                "amount": "300.00",
                "currency_code": "EUR",
                "status": "pending",
                "channel": "direct",
                "title": "Loyer avril",
                "note": "Appartement centre",
                "share_token": "PR-ADMIN",
                "due_at": None,
                "expires_at": None,
                "paid_at": None,
                "declined_at": None,
                "cancelled_at": None,
                "last_reminder_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "counterpart_label": None,
                "role": "admin",
                "requester_label": "@alice",
                "payer_label": "@bob",
            }
        ]

    async def fake_get_admin_payment_request_detail_v2(db, *, request_id):
        return {
            "request": {
                "request_id": str(request_id),
                "requester_user_id": str(uuid4()),
                "payer_user_id": str(uuid4()),
                "amount": "300.00",
                "currency_code": "EUR",
                "status": "pending",
                "channel": "direct",
                "title": "Loyer avril",
                "note": "Appartement centre",
                "share_token": "PR-ADMIN",
                "due_at": None,
                "expires_at": None,
                "paid_at": None,
                "declined_at": None,
                "cancelled_at": None,
                "last_reminder_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "counterpart_label": None,
                "role": "admin",
                "requester_label": "@alice",
                "payer_label": "@bob",
            },
            "events": [
                {
                    "event_id": str(uuid4()),
                    "actor_user_id": None,
                    "actor_role": "client",
                    "event_type": "sent",
                    "before_status": "pending",
                    "after_status": "pending",
                    "metadata": {},
                    "created_at": "2026-04-05T10:05:00Z",
                }
            ],
        }

    monkeypatch.setattr(admin_module, "list_admin_payment_requests_v2", fake_list_admin_payment_requests_v2)
    monkeypatch.setattr(admin_module, "get_admin_payment_request_detail_v2", fake_get_admin_payment_request_detail_v2)

    client = _build_test_client()

    response = client.get("/admin/payment-requests/v2?status=pending&q=loyer&limit=50")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["requester_label"] == "@alice"
    assert payload[0]["payer_label"] == "@bob"

    detail_response = client.get(f"/admin/payment-requests/v2/{request_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["request"]["title"] == "Loyer avril"
    assert detail["events"][0]["event_type"] == "sent"

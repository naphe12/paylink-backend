from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.business import router as business_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(business_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@client")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def test_business_payment_requests_create_list_and_detail(monkeypatch):
    from app.routers import business as business_module

    business_id = uuid4()
    request_id = uuid4()

    async def fake_create_business_payment_request(db, *, business_id, current_user, payload):
        assert payload.amount == 45
        return SimpleNamespace(request_id=request_id)

    async def fake_list_business_payment_requests(db, *, business_id, current_user, status=None, limit=100):
        return [
            {
                "request_id": str(request_id),
                "requester_user_id": str(uuid4()),
                "payer_user_id": None,
                "amount": "45.00",
                "currency_code": "USD",
                "status": "pending",
                "channel": "business_link",
                "title": "Commande #42",
                "note": "Paiement marchand",
                "share_token": "PR-BIZ1",
                "due_at": None,
                "expires_at": None,
                "paid_at": None,
                "declined_at": None,
                "cancelled_at": None,
                "last_reminder_at": None,
                "metadata": {"business_id": str(business_id), "merchant_reference": "CMD-42"},
                "created_at": "2026-04-06T10:00:00Z",
                "updated_at": "2026-04-06T10:00:00Z",
                "counterpart_label": None,
                "role": "business",
                "requester_label": "Alpha Shop",
                "payer_label": None,
            }
        ]

    async def fake_get_business_payment_request_detail(db, *, business_id, request_id, current_user):
        return {
            "request": (await fake_list_business_payment_requests(db, business_id=business_id, current_user=current_user))[0],
            "events": [
                {
                    "event_id": str(uuid4()),
                    "actor_user_id": str(current_user.user_id),
                    "actor_role": "client",
                    "event_type": "created",
                    "before_status": None,
                    "after_status": "pending",
                    "metadata": {},
                    "created_at": "2026-04-06T10:00:00Z",
                }
            ],
        }

    monkeypatch.setattr(business_module, "create_business_payment_request", fake_create_business_payment_request)
    monkeypatch.setattr(business_module, "list_business_payment_requests", fake_list_business_payment_requests)
    monkeypatch.setattr(business_module, "get_business_payment_request_detail", fake_get_business_payment_request_detail)

    client = _build_test_client()

    create_response = client.post(
        f"/business-accounts/{business_id}/payment-requests",
        json={
            "amount": 45,
            "currency_code": "USD",
            "title": "Commande #42",
            "note": "Paiement marchand",
            "merchant_reference": "CMD-42",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["share_token"] == "PR-BIZ1"

    list_response = client.get(f"/business-accounts/{business_id}/payment-requests?limit=50")
    assert list_response.status_code == 200
    assert list_response.json()[0]["requester_label"] == "Alpha Shop"

    detail_response = client.get(f"/business-accounts/{business_id}/payment-requests/{request_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["events"][0]["event_type"] == "created"

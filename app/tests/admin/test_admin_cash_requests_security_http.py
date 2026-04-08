from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.wallet_cash_requests import WalletCashRequestStatus, WalletCashRequestType
from app.routers.admin.cash_requests import router as admin_cash_requests_router


class _FakeDb:
    def __init__(self, request_obj):
        self.request_obj = request_obj
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def get(self, model, _pk):
        if model.__name__ == "WalletCashRequests":
            return self.request_obj
        return None


def _build_client(db, current_admin):
    app = FastAPI()
    app.include_router(admin_cash_requests_router)

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_admin_cash_request_reject_requires_step_up(monkeypatch):
    from app.dependencies import step_up as step_up_module

    request_obj = SimpleNamespace(
        request_id=uuid4(),
        status=WalletCashRequestStatus.PENDING,
        type=WalletCashRequestType.DEPOSIT,
        amount=10,
        total_amount=10,
        admin_note=None,
        processed_by=None,
        processed_at=None,
    )
    db = _FakeDb(request_obj)
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "prod")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False)

    response = client.post(f"/admin/cash-requests/{request_obj.request_id}/reject", json={"note": "nope"})

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "cash_request_reject"


def test_admin_cash_request_reject_accepts_header_step_up_and_audits(monkeypatch):
    from app.dependencies import step_up as step_up_module
    from app.routers.admin import cash_requests as cash_module

    captured = {}

    def fake_transition_cash_request_status(req, new_status):
        req.status = new_status

    class _Payload:
        def model_dump(self, mode="json"):
            return {
                "request_id": str(request_obj.request_id),
                "reference_code": "REQ-1",
                "type": "deposit",
                "status": "rejected",
                "amount": "10",
                "fee_amount": "0",
                "total_amount": "10",
                "currency_code": "EUR",
                "mobile_number": None,
                "provider_name": None,
                "note": None,
                "admin_note": "nope",
                "created_at": "2026-04-08T10:00:00Z",
                "processed_at": "2026-04-08T10:01:00Z",
                "user": {
                    "user_id": str(uuid4()),
                    "full_name": None,
                    "email": None,
                },
                "processed_by_admin": None,
            }

    async def fake_serialize_request(db, req):
        return _Payload()

    async def fake_audit_log(db, **kwargs):
        captured["action"] = kwargs.get("action")
        captured["entity_id"] = kwargs.get("entity_id")

    request_obj = SimpleNamespace(
        request_id=uuid4(),
        status=WalletCashRequestStatus.PENDING,
        type=WalletCashRequestType.DEPOSIT,
        amount=10,
        total_amount=10,
        admin_note=None,
        processed_by=None,
        processed_at=None,
    )
    db = _FakeDb(request_obj)
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")
    client = _build_client(db, current_admin)

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "dev")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", True)
    monkeypatch.setattr(cash_module, "transition_cash_request_status", fake_transition_cash_request_status)
    monkeypatch.setattr(cash_module, "_serialize_request", fake_serialize_request)
    monkeypatch.setattr(cash_module, "audit_log", fake_audit_log)

    response = client.post(
        f"/admin/cash-requests/{request_obj.request_id}/reject",
        headers={"X-Admin-Confirm": "confirm"},
        json={"note": "nope"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert captured["action"] == "ADMIN_CASH_REQUEST_REJECT"
    assert captured["entity_id"] == str(request_obj.request_id)

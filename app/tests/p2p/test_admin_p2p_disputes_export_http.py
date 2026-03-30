from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.p2p.admin_p2p import router as admin_p2p_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(admin_p2p_router, prefix="/api")
    db = _FakeDb()
    current_user = SimpleNamespace(user_id="admin-1", role="admin")

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_admin_p2p_disputes_export_json(monkeypatch):
    async def fake_collect_disputes(db, status=None):
        assert status == "OPEN"
        return [
            {
                "dispute_id": "disp-1",
                "source": "p2p",
                "trade_id": "trade-1",
                "status": "OPEN",
                "reason": "Buyer says payment was sent",
                "reason_code": "payment_not_received",
                "reason_code_label": "Payment not received",
                "resolution_code": None,
                "resolution_code_label": None,
                "proof_type": "screenshot",
                "proof_type_label": "Screenshot",
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_collect_disputes", fake_collect_disputes)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/disputes/export?format=json&status=OPEN")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "p2p_disputes_open.json" in response.headers["content-disposition"]
    assert response.json()[0]["dispute_id"] == "disp-1"
    assert response.json()[0]["reason_code_label"] == "Payment not received"
    assert response.json()[0]["proof_type_label"] == "Screenshot"


def test_admin_p2p_disputes_export_csv(monkeypatch):
    async def fake_collect_disputes(db, status=None):
        assert status is None
        return [
            {
                "dispute_id": "disp-2",
                "source": "p2p",
                "trade_id": "trade-2",
                "tx_id": None,
                "status": "RESOLVED_BUYER",
                "trade_status": "RELEASED",
                "created_at": "2026-03-29T10:00:00Z",
                "updated_at": None,
                "resolved_at": "2026-03-29T11:00:00Z",
                "opened_by_name": "Buyer A",
                "resolved_by_name": "Admin A",
                "buyer_name": "Buyer A",
                "seller_name": "Seller B",
                "token": "USDT",
                "token_amount": 100,
                "price_bif_per_usd": 2900,
                "bif_amount": 290000,
                "tx_amount": None,
                "tx_currency": None,
                "payment_method": "Lumicash",
                "reason": "Payment proof valid",
                "reason_code": "payment_not_received",
                "reason_code_label": "Payment not received",
                "resolution": "Buyer wins",
                "resolution_code": "payment_proof_validated",
                "resolution_code_label": "Payment proof validated",
                "proof_type": "screenshot",
                "proof_type_label": "Screenshot",
                "proof_ref": "https://example.com/proof.png",
                "evidence_url": None,
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_collect_disputes", fake_collect_disputes)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/disputes/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "p2p_disputes_all.csv" in response.headers["content-disposition"]
    body = response.text
    assert "dispute_id,source,trade_id" in body
    assert "disp-2" in body
    assert "payment_not_received" in body
    assert "Payment not received" in body
    assert "payment_proof_validated" in body
    assert "Payment proof validated" in body
    assert "Screenshot" in body

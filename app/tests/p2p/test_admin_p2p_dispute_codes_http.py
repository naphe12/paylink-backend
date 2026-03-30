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


def test_admin_dispute_codes_http():
    client = _build_test_client()
    response = client.get("/api/admin/p2p/disputes/codes")

    assert response.status_code == 200
    payload = response.json()
    assert "proof_types" in payload
    assert "escrow_refund_reason_codes" in payload
    assert "p2p_dispute_resolution_codes" in payload
    assert {"value": "screenshot", "label": "Screenshot"} in payload["proof_types"]
    assert {
        "value": "payment_proof_validated",
        "label": "Payment proof validated",
    } in payload["p2p_dispute_resolution_codes"]

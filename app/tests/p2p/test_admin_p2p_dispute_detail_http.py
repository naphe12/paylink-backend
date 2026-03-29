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


def test_admin_p2p_dispute_detail_http(monkeypatch):
    async def fake_collect_disputes(db, status=None):
        assert status is None
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

    async def fake_load_timeline(db, *, dispute_id, trade_id):
        assert dispute_id == "disp-1"
        assert trade_id == "trade-1"
        return [
            {
                "id": "audit-1",
                "action": "P2P_DISPUTE_OPENED",
                "reason_code": "payment_not_received",
                "reason_code_label": "Payment not received",
                "proof_type": "screenshot",
                "proof_type_label": "Screenshot",
                "step_up_method": "token",
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_collect_disputes", fake_collect_disputes)
    monkeypatch.setattr(admin_p2p_module, "_load_p2p_dispute_timeline", fake_load_timeline)

    client = _build_test_client()
    response = client.get("/api/admin/p2p/disputes/detail/disp-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dispute"]["dispute_id"] == "disp-1"
    assert payload["dispute"]["reason_code_label"] == "Payment not received"
    assert payload["dispute"]["proof_type_label"] == "Screenshot"
    assert payload["timeline"][0]["action"] == "P2P_DISPUTE_OPENED"
    assert payload["timeline"][0]["reason_code_label"] == "Payment not received"
    assert payload["timeline"][0]["proof_type_label"] == "Screenshot"
    assert payload["timeline"][0]["step_up_method"] == "token"


def test_admin_p2p_disputes_list_embeds_operator_workflow(monkeypatch):
    async def fake_fetch_p2p_rows(db):
        class _Rows:
            def mappings(self):
                return self

            def all(self):
                return [
                    {
                        "dispute_id": "disp-2",
                        "trade_id": "trade-2",
                        "tx_id": None,
                        "status": "OPEN",
                        "reason": "Need review",
                        "created_at": "2026-03-29T10:00:00Z",
                        "updated_at": None,
                        "resolved_at": None,
                        "opened_by_user_id": "user-1",
                        "opened_by_name": "User One",
                        "resolved_by_user_id": None,
                        "resolved_by_name": None,
                        "resolution": None,
                        "evidence_url": None,
                        "buyer_id": "buyer-1",
                        "buyer_name": "Buyer One",
                        "seller_id": "seller-1",
                        "seller_name": "Seller One",
                        "token": "USDT",
                        "token_amount": 10,
                        "price_bif_per_usd": 3000,
                        "bif_amount": 30000,
                        "payment_method": "Lumicash",
                        "trade_status": "DISPUTED",
                        "tx_amount": None,
                        "tx_currency": None,
                    }
                ]

        return _Rows()

    async def fake_fetch_legacy_rows(db):
        class _Rows:
            def mappings(self):
                return self

            def all(self):
                return []

        return _Rows()

    async def fake_fetch_workflow_map(db, *, entity_type, entity_ids):
        assert entity_type == "p2p_dispute"
        assert entity_ids == ["disp-2"]
        return {"disp-2": {"operator_status": "blocked", "owner_name": "Arbitrage Team"}}

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "fetch_p2p_dispute_rows", fake_fetch_p2p_rows)
    monkeypatch.setattr(admin_p2p_module, "fetch_legacy_dispute_rows", fake_fetch_legacy_rows)
    async def fake_enrich(db, item):
        return item

    monkeypatch.setattr(admin_p2p_module, "_enrich_p2p_dispute_from_audit", fake_enrich)
    monkeypatch.setattr(admin_p2p_module, "fetch_operator_workflow_map", fake_fetch_workflow_map)

    client = _build_test_client()
    response = client.get("/api/admin/p2p/disputes")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["operator_workflow"]["operator_status"] == "blocked"


def test_admin_legacy_dispute_detail_http(monkeypatch):
    async def fake_collect_disputes(db, status=None):
        assert status is None
        return [
            {
                "dispute_id": "disp-legacy-1",
                "source": "paylink",
                "trade_id": None,
                "tx_id": "tx-1",
                "status": "opened",
                "reason": "Legacy issue",
                "created_at": "2026-03-29T10:00:00Z",
                "updated_at": "2026-03-29T11:00:00Z",
                "evidence_url": "https://example.com/evidence.pdf",
                "opened_by_user_id": "user-1",
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_collect_disputes", fake_collect_disputes)

    client = _build_test_client()
    response = client.get("/api/admin/p2p/disputes/detail/disp-legacy-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dispute"]["dispute_id"] == "disp-legacy-1"
    assert payload["timeline"][0]["action"] == "LEGACY_DISPUTE_OPENED"
    assert payload["timeline"][0]["evidence_url"] == "https://example.com/evidence.pdf"
    assert payload["dispute"]["reason_code_label"] is None
    assert payload["timeline"][0]["reason_code_label"] is None

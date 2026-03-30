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


def test_admin_p2p_chain_deposits_export_json(monkeypatch):
    async def fake_list_chain_deposits(*args, **kwargs):
        assert kwargs["status"] == "matched"
        return [
            {
                "deposit_id": "dep-1",
                "status": "matched",
                "token": "USDT",
                "amount": 100,
                "trade_id": "trade-1",
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "list_chain_deposits", fake_list_chain_deposits)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/deposits/export?format=json&status=matched")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "p2p_chain_deposits_matched.json" in response.headers["content-disposition"]
    payload = response.json()
    assert payload[0]["deposit_id"] == "dep-1"
    assert payload[0]["trade_id"] == "trade-1"


def test_admin_p2p_chain_deposits_export_csv(monkeypatch):
    async def fake_list_chain_deposits(*args, **kwargs):
        assert kwargs["status"] is None
        return [
            {
                "deposit_id": "dep-2",
                "status": "suggested",
                "resolution": None,
                "network": "TRON",
                "token": "USDT",
                "amount": 50,
                "tx_hash": "0xabc",
                "log_index": 0,
                "to_address": "T123",
                "from_address": "T999",
                "escrow_deposit_ref": "P2P-REF-2",
                "trade_id": "trade-2",
                "trade_status": "AWAITING_FIAT",
                "matched_at": None,
                "matched_by": None,
                "block_number": 123,
                "confirmations": 12,
                "chain_id": 1,
                "source": "simulator",
                "source_ref": "sim-1",
                "provider": "SIMULATED",
                "provider_event_id": "evt-1",
                "suggestion_count": 2,
                "suggested_trades": [{"trade_id": "trade-2"}, {"trade_id": "trade-3"}],
                "created_at": "2026-03-29T10:00:00Z",
                "updated_at": "2026-03-29T10:05:00Z",
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "list_chain_deposits", fake_list_chain_deposits)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/deposits/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "p2p_chain_deposits_all.csv" in response.headers["content-disposition"]
    body = response.text
    assert "deposit_id,status,resolution" in body
    assert "dep-2" in body
    assert "P2P-REF-2" in body
    assert "trade-2|trade-3" in body

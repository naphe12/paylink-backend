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


def test_admin_p2p_trade_detail_http(monkeypatch):
    async def fake_get_admin_trade_detail(db, trade_id):
        assert trade_id == "trade-1"
        return {
            "trade_id": "trade-1",
            "offer_id": "offer-1",
            "status": "FIAT_SENT",
            "buyer_user_id": "buyer-1",
            "buyer_name": "Buyer A",
            "seller_user_id": "seller-1",
            "seller_name": "Seller B",
            "offer_owner_user_id": "seller-1",
            "offer_owner_name": "Seller B",
            "offer_side": "SELL",
            "token": "USDT",
            "token_amount": 100,
            "bif_amount": 290000,
            "payment_method": "Lumicash",
            "risk_score": 20,
            "flags": ["ok"],
            "escrow_network": "POLYGON",
            "escrow_deposit_addr": "0xabc",
            "escrow_deposit_ref": "P2P-REF-1",
            "escrow_provider": "SIMULATED",
            "escrow_tx_hash": "0xhash",
            "escrow_lock_log_index": 0,
            "fiat_sent_at": "2026-03-29T10:30:00Z",
            "fiat_confirmed_at": None,
            "disputes_count": 1,
        }

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_get_admin_trade_detail", fake_get_admin_trade_detail)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/trades/trade-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_id"] == "trade-1"
    assert payload["buyer_name"] == "Buyer A"
    assert payload["seller_name"] == "Seller B"
    assert payload["escrow_deposit_ref"] == "P2P-REF-1"
    assert payload["disputes_count"] == 1


def test_admin_p2p_trade_detail_not_found_http(monkeypatch):
    async def fake_get_admin_trade_detail(db, trade_id):
        assert trade_id == "missing"
        return None

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_get_admin_trade_detail", fake_get_admin_trade_detail)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/trades/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Trade not found"

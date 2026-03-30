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


def test_admin_p2p_trades_export_json(monkeypatch):
    async def fake_collect_admin_trades(db, status=None):
        assert status == "DISPUTED"
        return [
            {
                "trade_id": "trade-1",
                "offer_id": "offer-1",
                "status": "DISPUTED",
                "buyer_user_id": "buyer-1",
                "buyer_name": "Buyer A",
                "seller_user_id": "seller-1",
                "seller_name": "Seller B",
                "token": "USDT",
                "token_amount": 100,
                "bif_amount": 290000,
                "risk_score": 75,
                "disputes_count": 1,
                "flags": ["risk_high"],
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_collect_admin_trades", fake_collect_admin_trades)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/trades/export?format=json&status=DISPUTED")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "p2p_trades_disputed.json" in response.headers["content-disposition"]
    payload = response.json()
    assert payload[0]["trade_id"] == "trade-1"
    assert payload[0]["buyer_name"] == "Buyer A"
    assert payload[0]["seller_name"] == "Seller B"


def test_admin_p2p_trades_export_csv(monkeypatch):
    async def fake_collect_admin_trades(db, status=None):
        assert status is None
        return [
            {
                "trade_id": "trade-2",
                "offer_id": "offer-2",
                "status": "RELEASED",
                "created_at": "2026-03-29T10:00:00Z",
                "updated_at": "2026-03-29T11:00:00Z",
                "expires_at": "2026-03-29T12:00:00Z",
                "buyer_user_id": "buyer-2",
                "buyer_name": "Buyer B",
                "seller_user_id": "seller-2",
                "seller_name": "Seller C",
                "offer_owner_user_id": "seller-2",
                "offer_owner_name": "Seller C",
                "offer_side": "SELL",
                "payment_method": "Lumicash",
                "token": "USDC",
                "token_amount": 50,
                "price_bif_per_usd": 2900,
                "bif_amount": 145000,
                "risk_score": 12,
                "disputes_count": 0,
                "escrow_deposit_ref": "P2P-REF-1",
                "escrow_provider": "SIMULATED",
                "escrow_tx_hash": "0xabc",
                "escrow_lock_log_index": 0,
                "fiat_sent_at": "2026-03-29T10:30:00Z",
                "fiat_confirmed_at": "2026-03-29T10:45:00Z",
                "flags": ["ok", "fast"],
            }
        ]

    from app.routers.p2p import admin_p2p as admin_p2p_module

    monkeypatch.setattr(admin_p2p_module, "_collect_admin_trades", fake_collect_admin_trades)
    client = _build_test_client()

    response = client.get("/api/admin/p2p/trades/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "p2p_trades_all.csv" in response.headers["content-disposition"]
    body = response.text
    assert "trade_id,offer_id,status" in body
    assert "trade-2" in body
    assert "Buyer B" in body
    assert "Seller C" in body
    assert "P2P-REF-1" in body
    assert "ok|fast" in body

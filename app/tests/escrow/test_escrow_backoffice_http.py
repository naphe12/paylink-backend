from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.escrow.escrow_backoffice import router as escrow_backoffice_router


class _FakeDb:
    async def rollback(self):
        return None


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(escrow_backoffice_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id="admin-1", role="admin")

    async def override_get_db():
        return db

    async def override_get_current_user_db():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user_db
    return TestClient(app)


def test_backoffice_escrow_orders_http(monkeypatch):
    class _FakeRows:
        def mappings(self):
            return self

        def all(self):
            return [
                {
                    "id": "order-1",
                    "status": "REFUND_PENDING",
                    "user_id": "user-1",
                    "user_name": "Deposant A",
                    "trader_id": "operator-1",
                    "trader_name": "Operateur A",
                    "usdc_expected": 100,
                    "usdc_received": 100,
                    "usdt_target": 99,
                    "usdt_received": 99,
                    "bif_target": 290000,
                    "bif_paid": None,
                    "risk_score": 12,
                    "flags": ["review"],
                    "deposit_network": "POLYGON",
                    "deposit_address": "0xabc",
                    "deposit_tx_hash": "0xhash",
                    "payout_method": "LUMICASH",
                    "payout_provider": "Lumicash",
                    "payout_account_name": "Benef A",
                    "payout_account_number": "+25761234567",
                    "payout_reference": "REF-1",
                    "funded_at": None,
                    "swapped_at": None,
                    "payout_initiated_at": None,
                    "paid_out_at": None,
                    "created_at": "2026-03-29T10:00:00Z",
                    "updated_at": "2026-03-29T10:30:00Z",
                }
            ]

    async def fake_fetch_rows(db, **kwargs):
        assert kwargs["status"] is None
        assert kwargs["limit"] == 200
        return _FakeRows()

    from app.routers.escrow import escrow_backoffice as module

    monkeypatch.setattr(module, "fetch_escrow_order_rows", fake_fetch_rows)
    async def fake_fetch_operator_workflow_map(*args, **kwargs):
        return {"order-1": {"operator_status": "blocked", "owner_name": "Ops A"}}

    monkeypatch.setattr(module, "fetch_operator_workflow_map", fake_fetch_operator_workflow_map)
    client = _build_test_client()

    response = client.get("/backoffice/escrow/orders")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "order-1"
    assert payload[0]["depositor_name"] == "Deposant A"
    assert payload[0]["payout_operator_name"] == "Operateur A"
    assert payload[0]["payout_beneficiary_account"] == "+25761234567"
    assert payload[0]["operator_workflow"]["operator_status"] == "blocked"


def test_backoffice_escrow_order_detail_http(monkeypatch):
    class _FakeRowResult:
        def mappings(self):
            return self

        def first(self):
            return {
                "id": "order-2",
                "status": "REFUND_PENDING",
                "user_id": "user-2",
                "user_name": "Deposant B",
                "trader_id": "operator-2",
                "trader_name": "Operateur B",
                "usdc_expected": 200,
                "usdc_received": 200,
                "usdt_target": 198,
                "usdt_received": 198,
                "bif_target": 580000,
                "bif_paid": None,
                "risk_score": 20,
                "flags": [],
                "deposit_network": "POLYGON",
                "deposit_address": "0xdef",
                "deposit_tx_hash": "0xhash2",
                "payout_method": "LUMICASH",
                "payout_provider": "Lumicash",
                "payout_account_name": "Benef B",
                "payout_account_number": "+25769999999",
                "payout_reference": "REF-2",
                "funded_at": None,
                "swapped_at": None,
                "payout_initiated_at": None,
                "paid_out_at": None,
                "created_at": "2026-03-29T10:00:00Z",
                "updated_at": "2026-03-29T10:30:00Z",
            }

    async def fake_fetch_detail(db, order_id):
        assert order_id == "order-2"
        return _FakeRowResult()

    async def fake_load_refund_audit_trail(db, order_id):
        assert order_id == "order-2"
        return [{"action": "ESCROW_REFUND_REQUESTED"}]

    from app.routers.escrow import escrow_backoffice as module

    monkeypatch.setattr(module, "fetch_escrow_order_detail_row", fake_fetch_detail)
    monkeypatch.setattr(module, "_load_refund_audit_trail", fake_load_refund_audit_trail)
    async def fake_fetch_operator_workflow_map(*args, **kwargs):
        return {"order-2": {"operator_status": "needs_follow_up", "owner_name": "Ops B"}}

    monkeypatch.setattr(module, "fetch_operator_workflow_map", fake_fetch_operator_workflow_map)
    client = _build_test_client()

    response = client.get("/backoffice/escrow/orders/order-2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "order-2"
    assert payload["depositor_name"] == "Deposant B"
    assert payload["payout_operator_name"] == "Operateur B"
    assert payload["refund_audit_trail"][0]["action"] == "ESCROW_REFUND_REQUESTED"
    assert payload["operator_workflow"]["owner_name"] == "Ops B"

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db
from app.routers.escrow.escrow import router as escrow_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(escrow_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="admin")

    async def override_get_db():
        return db

    async def override_get_current_user_db():
        return current_user

    async def override_get_current_admin():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_request_escrow_refund_http(monkeypatch):
    order_id = uuid4()
    order = SimpleNamespace(id=order_id, status="SWAPPED")
    captured = {}

    async def fake_get_order(db, order_id_arg):
        assert str(order_id_arg) == str(order_id)
        return order

    async def fake_request_refund(
        db,
        order_arg,
        *,
        actor_user_id,
        actor_role,
        reason,
        reason_code=None,
        proof_type=None,
        proof_ref=None,
        step_up_method=None,
    ):
        captured["actor_user_id"] = actor_user_id
        captured["actor_role"] = actor_role
        captured["reason"] = reason
        captured["reason_code"] = reason_code
        captured["proof_type"] = proof_type
        captured["proof_ref"] = proof_ref
        captured["step_up_method"] = step_up_method
        order_arg.status = "REFUND_PENDING"
        return order_arg

    from app.routers.escrow import escrow as escrow_router_module

    monkeypatch.setattr(escrow_router_module.EscrowService, "get_order", fake_get_order)
    monkeypatch.setattr(escrow_router_module.EscrowDisputeService, "request_refund", fake_request_refund)

    client = _build_test_client()
    response = client.post(
        f"/escrow/orders/{order_id}/refund/request",
        json={"reason": "Payout failed on operator side"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["order_id"] == str(order_id)
    assert payload["escrow_status"] == "REFUND_PENDING"
    assert captured["actor_role"] == "admin"
    assert captured["reason"] == "Payout failed on operator side"
    assert captured["reason_code"] is None
    assert captured["proof_type"] is None
    assert captured["proof_ref"] is None
    assert captured["step_up_method"] is None


def test_request_escrow_refund_http_requires_step_up_when_enabled(monkeypatch):
    order_id = uuid4()

    from app.routers.escrow import escrow as escrow_router_module

    monkeypatch.setattr(escrow_router_module.settings, "ADMIN_STEP_UP_ENABLED", True)

    client = _build_test_client()
    response = client.post(
        f"/escrow/orders/{order_id}/refund/request",
        json={"reason": "Payout failed on operator side"},
    )

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "escrow_refund_request"
    assert payload["token_header_name"] == "X-Admin-Step-Up-Token"
    assert payload["header_fallback_enabled"] is False


def test_confirm_escrow_refund_http(monkeypatch):
    order_id = uuid4()
    order = SimpleNamespace(id=order_id, status="REFUND_PENDING")
    captured = {}

    async def fake_get_order(db, order_id_arg):
        assert str(order_id_arg) == str(order_id)
        return order

    async def fake_confirm_refund(
        db,
        order_arg,
        *,
        actor_user_id,
        actor_role,
        resolution,
        resolution_code=None,
        proof_type=None,
        proof_ref=None,
        step_up_method=None,
    ):
        captured["actor_user_id"] = actor_user_id
        captured["actor_role"] = actor_role
        captured["resolution"] = resolution
        captured["resolution_code"] = resolution_code
        captured["proof_type"] = proof_type
        captured["proof_ref"] = proof_ref
        captured["step_up_method"] = step_up_method
        order_arg.status = "REFUNDED"
        return order_arg

    from app.routers.escrow import escrow as escrow_router_module

    monkeypatch.setattr(escrow_router_module.EscrowService, "get_order", fake_get_order)
    monkeypatch.setattr(escrow_router_module.EscrowDisputeService, "confirm_refund", fake_confirm_refund)

    client = _build_test_client()
    response = client.post(
        f"/escrow/orders/{order_id}/refund/confirm",
        json={"resolution": "Refund approved after operator review"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["order_id"] == str(order_id)
    assert payload["escrow_status"] == "REFUNDED"
    assert captured["actor_role"] == "admin"
    assert captured["resolution"] == "Refund approved after operator review"
    assert captured["resolution_code"] is None
    assert captured["proof_type"] is None
    assert captured["proof_ref"] is None
    assert captured["step_up_method"] is None


def test_request_escrow_refund_http_passes_step_up_method(monkeypatch):
    order_id = uuid4()
    order = SimpleNamespace(id=order_id, status="SWAPPED")
    captured = {}

    async def fake_get_order(db, order_id_arg):
        return order

    async def fake_request_refund(
        db,
        order_arg,
        *,
        actor_user_id,
        actor_role,
        reason,
        reason_code=None,
        proof_type=None,
        proof_ref=None,
        step_up_method=None,
    ):
        captured["step_up_method"] = step_up_method
        order_arg.status = "REFUND_PENDING"
        return order_arg

    from app.dependencies import step_up as step_up_module
    from app.routers.escrow import escrow as escrow_router_module

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "APP_ENV", "dev")
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", True)
    monkeypatch.setattr(escrow_router_module.EscrowService, "get_order", fake_get_order)
    monkeypatch.setattr(escrow_router_module.EscrowDisputeService, "request_refund", fake_request_refund)

    client = _build_test_client()
    response = client.post(
        f"/escrow/orders/{order_id}/refund/request",
        headers={"X-Admin-Confirm": "confirm"},
        json={"reason": "Payout failed on operator side"},
    )

    assert response.status_code == 200
    assert captured["step_up_method"] == "header"

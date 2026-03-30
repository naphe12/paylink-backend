from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.p2p.p2p import router as p2p_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(p2p_router, prefix="/api")
    db = _FakeDb()
    current_user = SimpleNamespace(user_id="admin-1", role="admin")

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_resolve_p2p_dispute_requires_step_up_when_enabled(monkeypatch):
    from app.dependencies import step_up as step_up_module

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)

    client = _build_test_client()
    response = client.post(
        "/api/p2p/trades/trade-1/dispute/resolve",
        json={"outcome": "buyer_wins", "resolution": "Payment proof validated"},
    )

    assert response.status_code == 428
    payload = response.json()["detail"]
    assert payload["code"] == "admin_step_up_required"
    assert payload["action"] == "p2p_dispute_resolve"
    assert payload["token_header_name"] == "X-Admin-Step-Up-Token"
    assert payload["header_fallback_enabled"] is False


def test_resolve_p2p_dispute_accepts_step_up_header_when_fallback_enabled(monkeypatch):
    captured = {}

    async def fake_resolve_dispute(
        db,
        *,
        trade_id,
        resolved_by,
        outcome,
        resolution,
        resolution_code=None,
        proof_type=None,
        proof_ref=None,
        step_up_method=None,
    ):
        captured["trade_id"] = trade_id
        captured["resolved_by"] = resolved_by
        captured["outcome"] = outcome
        captured["resolution"] = resolution
        captured["step_up_method"] = step_up_method
        return SimpleNamespace(dispute_id="disp-1", status="RESOLVED_BUYER")

    from app.routers.p2p import p2p as p2p_router_module

    from app.dependencies import step_up as step_up_module

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", True)
    monkeypatch.setattr(p2p_router_module.P2PDisputeService, "resolve_dispute", fake_resolve_dispute)

    client = _build_test_client()
    response = client.post(
        "/api/p2p/trades/trade-1/dispute/resolve",
        headers={"X-Admin-Confirm": "confirm"},
        json={"outcome": "buyer_wins", "resolution": "Payment proof validated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["trade_id"] == "trade-1"
    assert captured["resolved_by"] == "admin-1"
    assert captured["step_up_method"] == "header"


def test_resolve_p2p_dispute_accepts_step_up_token(monkeypatch):
    captured = {}

    async def fake_resolve_dispute(
        db,
        *,
        trade_id,
        resolved_by,
        outcome,
        resolution,
        resolution_code=None,
        proof_type=None,
        proof_ref=None,
        step_up_method=None,
    ):
        captured["resolved_by"] = resolved_by
        captured["step_up_method"] = step_up_method
        return SimpleNamespace(dispute_id="disp-1", status="RESOLVED_BUYER")

    from app.dependencies import step_up as step_up_module
    from app.routers.p2p import p2p as p2p_router_module

    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ENABLED", True)
    monkeypatch.setattr(step_up_module.settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False)
    monkeypatch.setattr(p2p_router_module.P2PDisputeService, "resolve_dispute", fake_resolve_dispute)

    token = step_up_module.create_admin_step_up_token(
        user=SimpleNamespace(user_id="admin-1", role="admin"),
        action="p2p_dispute_resolve",
    )

    client = _build_test_client()
    response = client.post(
        "/api/p2p/trades/trade-1/dispute/resolve",
        headers={"X-Admin-Step-Up-Token": token},
        json={"outcome": "buyer_wins", "resolution": "Payment proof validated"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "OK"
    assert captured["resolved_by"] == "admin-1"
    assert captured["step_up_method"] == "token"

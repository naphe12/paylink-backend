from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.routers.admin.ops_workflow import router as ops_workflow_router


class _FakeDb:
    async def commit(self):
        return None


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(ops_workflow_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="admin")

    async def override_get_db():
        return db

    async def override_get_current_admin():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_put_operator_work_item_http(monkeypatch):
    expected_entity_id = uuid4()

    async def fake_ensure_entity_exists(db, *, entity_type, entity_id):
        assert entity_type == "payment_intent"
        assert entity_id == str(expected_entity_id)

    async def fake_upsert(db, *, entity_type, entity_id, changes):
        assert entity_type == "payment_intent"
        assert changes["operator_status"] == "blocked"
        return {
            "work_item_id": str(uuid4()),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "operator_status": "blocked",
            "owner_user_id": None,
            "owner_name": None,
            "blocked_reason": "Awaiting provider answer",
            "notes": None,
            "follow_up_at": None,
            "last_action_at": "2026-03-29T12:00:00Z",
            "created_at": "2026-03-29T12:00:00Z",
            "updated_at": "2026-03-29T12:00:00Z",
        }

    from app.routers.admin import ops_workflow as module

    monkeypatch.setattr(module, "_ensure_entity_exists", fake_ensure_entity_exists)
    monkeypatch.setattr(module, "upsert_operator_work_item", fake_upsert)

    client = _build_test_client()
    response = client.put(
        f"/admin/ops/work-items/payment_intent/{expected_entity_id}",
        json={"operator_status": "blocked", "blocked_reason": "Awaiting provider answer"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_type"] == "payment_intent"
    assert payload["operator_status"] == "blocked"
    assert payload["blocked_reason"] == "Awaiting provider answer"


def test_get_operator_workflow_summary_http(monkeypatch):
    expected_user_id = uuid4()

    async def override_get_current_admin():
        return SimpleNamespace(user_id=expected_user_id, role="admin", full_name="Admin Ops")

    async def fake_fetch_summary(db, *, current_user_id, current_owner_label):
        assert current_user_id == str(expected_user_id)
        assert current_owner_label == "Admin Ops"
        return {
            "all": 4,
            "mine": 1,
            "team": 3,
            "unassigned": 1,
            "blocked_only": 2,
            "needs_follow_up": 1,
            "watching": 1,
            "resolved": 0,
            "overdue_follow_up": 2,
            "owner_breakdown": [
                {
                    "owner_key": "admin ops",
                    "owner_label": "Admin Ops",
                    "count": 1,
                    "blocked_count": 1,
                    "overdue_follow_up_count": 0,
                    "mine": True,
                }
            ],
        }

    from app.dependencies.auth import get_current_admin as current_admin_dep
    from app.routers.admin import ops_workflow as module

    monkeypatch.setattr(module, "fetch_operator_workflow_summary", fake_fetch_summary)

    client = _build_test_client()
    client.app.dependency_overrides[current_admin_dep] = override_get_current_admin
    response = client.get("/admin/ops/work-items/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["all"] == 4
    assert payload["mine"] == 1
    assert payload["owner_breakdown"][0]["owner_label"] == "Admin Ops"


def test_get_operator_urgencies_http(monkeypatch):
    async def fake_fetch_urgencies(db):
        return [
            {
                "id": "escrow:11111111-1111-1111-1111-111111111111",
                "entity_type": "escrow_order",
                "entity_id": "11111111-1111-1111-1111-111111111111",
                "kind": "escrow",
                "title": "order-1",
                "subtitle": "Alice -> Trader One",
                "status": "REFUND_PENDING",
                "priority": "critical",
                "operator_status": "blocked",
                "age": "4h",
                "stale": True,
                "owner": "Ops Escrow",
                "last_action_at": "2026-03-29T12:00:00Z",
                "to": "/dashboard/admin/escrow?queue=stale",
                "meta": "Beneficiary not reachable",
                "operator_workflow": None,
            }
        ]

    from app.routers.admin import ops_workflow as module

    monkeypatch.setattr(module, "fetch_operator_urgency_items", fake_fetch_urgencies)

    client = _build_test_client()
    response = client.get("/admin/ops/work-items/urgencies")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["entity_type"] == "escrow_order"
    assert payload[0]["priority"] == "critical"
    assert payload[0]["to"] == "/dashboard/admin/escrow?queue=stale"


def test_get_operator_urgencies_http_with_filters(monkeypatch):
    expected_user_id = uuid4()

    async def override_get_current_admin():
        return SimpleNamespace(user_id=expected_user_id, role="admin", full_name="Admin Ops")

    async def fake_fetch_urgencies(db):
        return [{"id": "x"}]

    def fake_filter(items, **kwargs):
        assert items == [{"id": "x"}]
        assert kwargs["kind"] == "escrow"
        assert kwargs["operator_status"] == "blocked"
        assert kwargs["owner_key"] == "desk arbitrage"
        assert kwargs["view"] == "team"
        assert kwargs["q"] == "alice"
        assert kwargs["current_user_id"] == str(expected_user_id)
        assert kwargs["current_owner_label"] == "Admin Ops"
        return [
            {
                "id": "escrow:11111111-1111-1111-1111-111111111111",
                "entity_type": "escrow_order",
                "entity_id": "11111111-1111-1111-1111-111111111111",
                "kind": "escrow",
                "title": "filtered",
                "subtitle": "Alice -> Trader One",
                "status": "REFUND_PENDING",
                "priority": "critical",
                "operator_status": "blocked",
                "age": "4h",
                "stale": True,
                "owner": "Desk Arbitrage",
                "last_action_at": "2026-03-29T12:00:00Z",
                "to": "/dashboard/admin/escrow?queue=stale",
                "meta": "Filtered",
                "operator_workflow": None,
            }
        ]

    from app.dependencies.auth import get_current_admin as current_admin_dep
    from app.routers.admin import ops_workflow as module

    monkeypatch.setattr(module, "fetch_operator_urgency_items", fake_fetch_urgencies)
    monkeypatch.setattr(module, "filter_operator_urgency_items", fake_filter)

    client = _build_test_client()
    client.app.dependency_overrides[current_admin_dep] = override_get_current_admin
    response = client.get(
        "/admin/ops/work-items/urgencies?kind=escrow&operator_status=blocked&owner_key=desk%20arbitrage&view=team&q=alice"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["title"] == "filtered"
    assert payload[0]["owner"] == "Desk Arbitrage"

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
    monkeypatch.setattr(module, "summarize_operator_urgency_owner_load", lambda items: [{"owner_key": "ops escrow", "owner_label": "Ops Escrow", "count": 1, "blocked_count": 1, "overdue_follow_up_count": 0, "critical_count": 1}])
    monkeypatch.setattr(module, "summarize_operator_urgency_queues", lambda items: [{"kind": "escrow", "total": 1, "blocked_count": 1, "overdue_follow_up_count": 0, "stale_count": 1, "critical_count": 1}])
    monkeypatch.setattr(module, "sort_operator_urgency_items", lambda items, **kwargs: items)
    monkeypatch.setattr(module, "paginate_operator_urgency_items", lambda items, **kwargs: items)

    client = _build_test_client()
    response = client.get("/admin/ops/work-items/urgencies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["entity_type"] == "escrow_order"
    assert payload["items"][0]["priority"] == "critical"
    assert payload["items"][0]["to"] == "/dashboard/admin/escrow?queue=stale"
    assert payload["queue_summary"][0]["kind"] == "escrow"
    assert payload["owner_load"][0]["owner_label"] == "Ops Escrow"


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
    monkeypatch.setattr(module, "summarize_operator_urgency_owner_load", lambda items: [{"owner_key": "desk arbitrage", "owner_label": "Desk Arbitrage", "count": 1, "blocked_count": 1, "overdue_follow_up_count": 0, "critical_count": 1}])
    monkeypatch.setattr(module, "summarize_operator_urgency_queues", lambda items: [{"kind": "escrow", "total": 1, "blocked_count": 1, "overdue_follow_up_count": 0, "stale_count": 1, "critical_count": 1}])

    def fake_sort(items, **kwargs):
        assert kwargs["sort_by"] == "last_action_at"
        assert kwargs["sort_dir"] == "desc"
        return items

    def fake_paginate(items, **kwargs):
        assert kwargs["limit"] == 50
        assert kwargs["offset"] == 0
        return items

    monkeypatch.setattr(module, "sort_operator_urgency_items", fake_sort)
    monkeypatch.setattr(module, "paginate_operator_urgency_items", fake_paginate)

    client = _build_test_client()
    client.app.dependency_overrides[current_admin_dep] = override_get_current_admin
    response = client.get(
        "/admin/ops/work-items/urgencies?kind=escrow&operator_status=blocked&owner_key=desk%20arbitrage&view=team&q=alice"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["title"] == "filtered"
    assert payload["items"][0]["owner"] == "Desk Arbitrage"
    assert payload["owner_load"][0]["owner_key"] == "desk arbitrage"


def test_batch_upsert_operator_work_items_http(monkeypatch):
    first_id = uuid4()
    second_id = uuid4()
    calls = []

    async def fake_ensure_entity_exists(db, *, entity_type, entity_id):
        calls.append(("ensure", entity_type, entity_id))

    async def fake_upsert(db, *, entity_type, entity_id, changes):
        calls.append(("upsert", entity_type, entity_id, changes))
        return {
            "work_item_id": str(uuid4()),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "operator_status": changes["operator_status"],
            "owner_user_id": None,
            "owner_name": None,
            "blocked_reason": changes.get("blocked_reason"),
            "notes": changes.get("notes"),
            "follow_up_at": None,
            "last_action_at": "2026-03-29T12:00:00Z",
            "created_at": "2026-03-29T12:00:00Z",
            "updated_at": "2026-03-29T12:00:00Z",
        }

    from app.routers.admin import ops_workflow as module

    monkeypatch.setattr(module, "_ensure_entity_exists", fake_ensure_entity_exists)
    monkeypatch.setattr(module, "upsert_operator_work_item", fake_upsert)

    client = _build_test_client()
    response = client.post(
        "/admin/ops/work-items/batch",
        json={
            "targets": [
                {"entity_type": "payment_intent", "entity_id": str(first_id)},
                {"entity_type": "payment_intent", "entity_id": str(second_id)},
            ],
            "operator_status": "blocked",
            "blocked_reason": "Provider outage",
            "notes": "Batch action",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] == 2
    assert len(payload["items"]) == 2
    assert calls[0] == ("ensure", "payment_intent", str(first_id))
    assert calls[2] == ("ensure", "payment_intent", str(second_id))
    assert calls[1][3]["operator_status"] == "blocked"
    assert calls[1][3]["blocked_reason"] == "Provider outage"

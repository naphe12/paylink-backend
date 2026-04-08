from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db
from app.routers.admin.support_cases import router as admin_support_cases_router
from app.routers.support import router as support_cases_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(support_cases_router)
    app.include_router(admin_support_cases_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@client")
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com", paytag="@admin")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    async def override_get_current_admin():
        return current_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    return TestClient(app)


def test_client_support_cases_create_list_detail_and_reply(monkeypatch):
    from app.routers import support as support_module

    case_id = uuid4()
    user_id = uuid4()

    async def fake_create_support_case(db, *, current_user, category, subject, description, entity_type=None, entity_id=None):
        assert category == "wallet"
        assert subject == "Blocage wallet"
        assert description == "Le retrait reste pending"
        return {
            "case_id": str(case_id),
            "user_id": str(user_id),
            "assigned_to_user_id": None,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "category": category,
            "subject": subject,
            "description": description,
            "status": "open",
            "priority": "normal",
            "reason_code": None,
            "resolution_code": None,
            "sla_due_at": None,
            "first_response_at": None,
            "resolved_at": None,
            "closed_at": None,
            "metadata": {},
            "created_at": "2026-04-05T10:00:00Z",
            "updated_at": "2026-04-05T10:00:00Z",
            "customer_label": "@client",
            "assigned_to_label": None,
        }

    async def fake_list_support_cases_for_user(db, *, current_user, status=None):
        assert status == "open"
        return [
            {
                "case_id": str(case_id),
                "user_id": str(user_id),
                "assigned_to_user_id": None,
                "entity_type": None,
                "entity_id": None,
                "category": "wallet",
                "subject": "Blocage wallet",
                "description": "Le retrait reste pending",
                "status": "open",
                "priority": "normal",
                "reason_code": None,
                "resolution_code": None,
                "sla_due_at": None,
                "first_response_at": None,
                "resolved_at": None,
                "closed_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "customer_label": "@client",
                "assigned_to_label": None,
            }
        ]

    async def fake_get_support_case_detail_for_user(db, *, case_id, current_user):
        return {
            "case": {
                "case_id": str(case_id),
                "user_id": str(user_id),
                "assigned_to_user_id": None,
                "entity_type": None,
                "entity_id": None,
                "category": "wallet",
                "subject": "Blocage wallet",
                "description": "Le retrait reste pending",
                "status": "open",
                "priority": "normal",
                "reason_code": None,
                "resolution_code": None,
                "sla_due_at": None,
                "first_response_at": None,
                "resolved_at": None,
                "closed_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "customer_label": "@client",
                "assigned_to_label": None,
            },
            "messages": [
                {
                    "message_id": str(uuid4()),
                    "case_id": str(case_id),
                    "author_user_id": None,
                    "author_role": "client",
                    "message_type": "comment",
                    "body": "Le retrait reste pending",
                    "is_visible_to_customer": True,
                    "metadata": {},
                    "created_at": "2026-04-05T10:01:00Z",
                }
            ],
            "events": [
                {
                    "event_id": str(uuid4()),
                    "case_id": str(case_id),
                    "actor_user_id": None,
                    "actor_role": "client",
                    "event_type": "created",
                    "before_status": None,
                    "after_status": "open",
                    "metadata": {},
                    "created_at": "2026-04-05T10:00:00Z",
                }
            ],
        }

    async def fake_add_support_case_message_for_user(db, *, case_id, current_user, body):
        assert body == "Pouvez-vous verifier?"
        return await fake_get_support_case_detail_for_user(db, case_id=case_id, current_user=current_user)

    async def fake_update_support_case_status_for_user(db, *, case_id, current_user, action, message=None):
        assert action == "close"
        assert message is None
        payload = await fake_get_support_case_detail_for_user(db, case_id=case_id, current_user=current_user)
        payload["case"]["status"] = "closed"
        return payload

    monkeypatch.setattr(support_module, "create_support_case", fake_create_support_case)
    monkeypatch.setattr(support_module, "list_support_cases_for_user", fake_list_support_cases_for_user)
    monkeypatch.setattr(support_module, "get_support_case_detail_for_user", fake_get_support_case_detail_for_user)
    monkeypatch.setattr(support_module, "add_support_case_message_for_user", fake_add_support_case_message_for_user)
    monkeypatch.setattr(support_module, "update_support_case_status_for_user", fake_update_support_case_status_for_user)

    client = _build_test_client()

    create_response = client.post(
        "/support/cases",
        json={"category": "wallet", "subject": "Blocage wallet", "description": "Le retrait reste pending"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["subject"] == "Blocage wallet"

    list_response = client.get("/support/cases?status=open")
    assert list_response.status_code == 200
    assert list_response.json()[0]["status"] == "open"

    detail_response = client.get(f"/support/cases/{case_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["events"][0]["event_type"] == "created"

    reply_response = client.post(f"/support/cases/{case_id}/messages", json={"body": "Pouvez-vous verifier?"})
    assert reply_response.status_code == 200
    assert reply_response.json()["messages"][0]["body"] == "Le retrait reste pending"

    status_response = client.post(f"/support/cases/{case_id}/status", json={"action": "close"})
    assert status_response.status_code == 200
    assert status_response.json()["case"]["status"] == "closed"


def test_admin_support_cases_list_detail_assign_status_and_reply(monkeypatch):
    from app.routers.admin import support_cases as admin_module

    case_id = uuid4()

    async def fake_list_support_cases_admin(db, *, status=None, q=None, limit=200):
        assert status == "open"
        assert q == "wallet"
        assert limit == 50
        return [
            {
                "case_id": str(case_id),
                "user_id": str(uuid4()),
                "assigned_to_user_id": None,
                "entity_type": None,
                "entity_id": None,
                "category": "wallet",
                "subject": "Blocage wallet",
                "description": "Le retrait reste pending",
                "status": "open",
                "priority": "normal",
                "reason_code": None,
                "resolution_code": None,
                "sla_due_at": None,
                "first_response_at": None,
                "resolved_at": None,
                "closed_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "customer_label": "@bob",
                "assigned_to_label": None,
            }
        ]

    async def fake_get_support_case_detail_admin(db, *, case_id):
        return {
            "case": {
                "case_id": str(case_id),
                "user_id": str(uuid4()),
                "assigned_to_user_id": None,
                "entity_type": None,
                "entity_id": None,
                "category": "wallet",
                "subject": "Blocage wallet",
                "description": "Le retrait reste pending",
                "status": "open",
                "priority": "normal",
                "reason_code": None,
                "resolution_code": None,
                "sla_due_at": None,
                "first_response_at": None,
                "resolved_at": None,
                "closed_at": None,
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "customer_label": "@bob",
                "assigned_to_label": None,
            },
            "messages": [],
            "events": [],
        }

    async def fake_assign_support_case_admin(db, *, case_id, admin_user, assigned_to_user_id):
        assert str(assigned_to_user_id) == "11111111-1111-1111-1111-111111111111"
        return await fake_get_support_case_detail_admin(db, case_id=case_id)

    async def fake_update_support_case_status_admin(
        db,
        *,
        case_id,
        admin_user,
        status,
        resolution_code=None,
        reason_code=None,
        message=None,
    ):
        assert status == "resolved"
        assert message == "Incident cloture"
        return await fake_get_support_case_detail_admin(db, case_id=case_id)

    async def fake_reply_support_case_admin(db, *, case_id, admin_user, body):
        assert body == "Nous analysons le dossier"
        return await fake_get_support_case_detail_admin(db, case_id=case_id)

    monkeypatch.setattr(admin_module, "list_support_cases_admin", fake_list_support_cases_admin)
    monkeypatch.setattr(admin_module, "get_support_case_detail_admin", fake_get_support_case_detail_admin)
    monkeypatch.setattr(admin_module, "assign_support_case_admin", fake_assign_support_case_admin)
    monkeypatch.setattr(admin_module, "update_support_case_status_admin", fake_update_support_case_status_admin)
    monkeypatch.setattr(admin_module, "reply_support_case_admin", fake_reply_support_case_admin)

    client = _build_test_client()

    list_response = client.get("/admin/support-cases?status=open&q=wallet&limit=50")
    assert list_response.status_code == 200
    assert list_response.json()[0]["customer_label"] == "@bob"

    detail_response = client.get(f"/admin/support-cases/{case_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["case"]["subject"] == "Blocage wallet"

    assign_response = client.post(
        f"/admin/support-cases/{case_id}/assign",
        json={"assigned_to_user_id": "11111111-1111-1111-1111-111111111111"},
    )
    assert assign_response.status_code == 200

    status_response = client.post(
        f"/admin/support-cases/{case_id}/status",
        json={"status": "resolved", "message": "Incident cloture"},
    )
    assert status_response.status_code == 200

    reply_response = client.post(
        f"/admin/support-cases/{case_id}/reply",
        json={"body": "Nous analysons le dossier"},
    )
    assert reply_response.status_code == 200

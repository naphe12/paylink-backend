from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.wallet.scheduled_transfers import router as scheduled_transfers_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(scheduled_transfers_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com", paytag="@client")

    async def override_get_db():
        return db

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user
    return TestClient(app)


def _schedule_payload(schedule_id, user_id, **overrides):
    payload = {
        "schedule_id": str(schedule_id),
        "user_id": str(user_id),
        "receiver_user_id": str(uuid4()),
        "receiver_identifier": "@bob",
        "transfer_type": "internal",
        "external_transfer": None,
        "amount": "2500.00",
        "currency_code": "BIF",
        "frequency": "weekly",
        "status": "active",
        "note": "Loyer",
        "next_run_at": "2026-04-08T08:00:00Z",
        "last_run_at": None,
        "last_result": None,
        "remaining_runs": 4,
        "is_due": False,
        "metadata": {},
        "created_at": "2026-04-06T10:00:00Z",
        "updated_at": "2026-04-06T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_scheduled_transfer_routes_cover_lifecycle(monkeypatch):
    from app.routers.wallet import scheduled_transfers as scheduled_module

    schedule_id = uuid4()

    async def fake_list_scheduled_transfers(db, *, current_user):
        return [_schedule_payload(schedule_id, current_user.user_id)]

    async def fake_create_scheduled_transfer(db, *, current_user, payload):
        assert payload.receiver_identifier == "@bob"
        assert payload.frequency == "weekly"
        return _schedule_payload(schedule_id, current_user.user_id)

    async def fake_run_due_scheduled_transfers(db, *, current_user):
        return [
            _schedule_payload(
                schedule_id,
                current_user.user_id,
                last_run_at="2026-04-08T08:00:00Z",
                last_result="success",
                next_run_at="2026-04-15T08:00:00Z",
            )
        ]

    async def fake_run_scheduled_transfer_now(db, *, current_user, schedule_id):
        return _schedule_payload(
            schedule_id,
            current_user.user_id,
            last_run_at="2026-04-06T10:05:00Z",
            last_result="success",
        )

    async def fake_cancel_scheduled_transfer(db, *, current_user, schedule_id):
        return _schedule_payload(schedule_id, current_user.user_id, status="cancelled")

    async def fake_pause_scheduled_transfer(db, *, current_user, schedule_id):
        return _schedule_payload(schedule_id, current_user.user_id, status="paused")

    async def fake_resume_scheduled_transfer(db, *, current_user, schedule_id):
        return _schedule_payload(schedule_id, current_user.user_id, status="active")

    async def fake_update_scheduled_transfer(db, *, current_user, schedule_id, payload):
        assert payload.frequency == "monthly"
        return _schedule_payload(
            schedule_id,
            current_user.user_id,
            frequency="monthly",
            next_run_at="2026-05-08T08:00:00Z",
        )

    monkeypatch.setattr(scheduled_module, "list_scheduled_transfers", fake_list_scheduled_transfers)
    monkeypatch.setattr(scheduled_module, "create_scheduled_transfer", fake_create_scheduled_transfer)
    monkeypatch.setattr(scheduled_module, "update_scheduled_transfer", fake_update_scheduled_transfer)
    monkeypatch.setattr(scheduled_module, "run_due_scheduled_transfers", fake_run_due_scheduled_transfers)
    monkeypatch.setattr(scheduled_module, "run_scheduled_transfer_now", fake_run_scheduled_transfer_now)
    monkeypatch.setattr(scheduled_module, "cancel_scheduled_transfer", fake_cancel_scheduled_transfer)
    monkeypatch.setattr(scheduled_module, "pause_scheduled_transfer", fake_pause_scheduled_transfer)
    monkeypatch.setattr(scheduled_module, "resume_scheduled_transfer", fake_resume_scheduled_transfer)

    client = _build_test_client()

    list_response = client.get("/wallet/scheduled-transfers")
    assert list_response.status_code == 200
    assert list_response.json()[0]["receiver_identifier"] == "@bob"

    create_response = client.post(
        "/wallet/scheduled-transfers",
        json={
            "receiver_identifier": "@bob",
            "amount": 2500,
            "frequency": "weekly",
            "next_run_at": "2026-04-08T08:00:00Z",
            "remaining_runs": 4,
            "note": "Loyer",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["frequency"] == "weekly"

    update_response = client.put(
        f"/wallet/scheduled-transfers/{schedule_id}",
        json={"frequency": "monthly", "next_run_at": "2026-05-08T08:00:00Z"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["frequency"] == "monthly"

    run_due_response = client.post("/wallet/scheduled-transfers/run-due")
    assert run_due_response.status_code == 200
    assert run_due_response.json()[0]["last_result"] == "success"

    run_now_response = client.post(f"/wallet/scheduled-transfers/{schedule_id}/run")
    assert run_now_response.status_code == 200
    assert run_now_response.json()["last_run_at"] == "2026-04-06T10:05:00Z"

    pause_response = client.post(f"/wallet/scheduled-transfers/{schedule_id}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"

    resume_response = client.post(f"/wallet/scheduled-transfers/{schedule_id}/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "active"

    cancel_response = client.post(f"/wallet/scheduled-transfers/{schedule_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_scheduled_transfer_routes_support_external_payload(monkeypatch):
    from app.routers.wallet import scheduled_transfers as scheduled_module

    schedule_id = uuid4()

    async def fake_create_scheduled_transfer(db, *, current_user, payload):
        assert payload.transfer_type == "external"
        assert payload.external_transfer.partner_name == "Lumicash"
        assert payload.external_transfer.country_destination == "Burundi"
        assert payload.external_transfer.recipient_phone == "+25761234567"
        return _schedule_payload(
            schedule_id,
            current_user.user_id,
            receiver_user_id=None,
            receiver_identifier="+25761234567",
            transfer_type="external",
            external_transfer={
                "partner_name": "Lumicash",
                "country_destination": "Burundi",
                "recipient_name": "Jean Ndayishimiye",
                "recipient_phone": "+25761234567",
                "recipient_email": "jean@example.com",
            },
            amount="125.00",
            currency_code="EUR",
            frequency="monthly",
            note="Famille",
        )

    monkeypatch.setattr(scheduled_module, "create_scheduled_transfer", fake_create_scheduled_transfer)

    client = _build_test_client()
    response = client.post(
        "/wallet/scheduled-transfers",
        json={
            "transfer_type": "external",
            "amount": 125,
            "frequency": "monthly",
            "next_run_at": "2026-04-08T08:00:00Z",
            "note": "Famille",
            "external_transfer": {
                "partner_name": "Lumicash",
                "country_destination": "Burundi",
                "recipient_name": "Jean Ndayishimiye",
                "recipient_phone": "+25761234567",
                "recipient_email": "jean@example.com",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["transfer_type"] == "external"
    assert response.json()["external_transfer"]["partner_name"] == "Lumicash"


def test_scheduled_transfer_routes_reject_invalid_frequency():
    client = _build_test_client()
    response = client.post(
        "/wallet/scheduled-transfers",
        json={
            "receiver_identifier": "@bob",
            "amount": 2500,
            "frequency": "yearly",
            "next_run_at": "2026-04-08T08:00:00Z",
        },
    )

    assert response.status_code == 422

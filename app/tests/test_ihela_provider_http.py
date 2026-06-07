from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.routers.providers import ihela


def _build_test_client(role: str = "admin") -> TestClient:
    app = FastAPI()
    app.include_router(ihela.router)
    current_user = SimpleNamespace(user_id="user-1", role=role)

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return TestClient(app)


def test_ihela_test_withdrawal_uses_bridge_when_configured(monkeypatch):
    calls = []

    async def fake_bridge_post(path, payload):
        calls.append((path, payload))
        return 200, {
            "response_data": {
                "reference": "IH-REF-001",
            },
        }

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "https://bridge.example.test")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "bridge-key")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_WITHDRAWAL_PATH", "/ihela/transfer")
    monkeypatch.setattr(ihela, "_bridge_post", fake_bridge_post)

    client = _build_test_client(role="admin")
    response = client.post(
        "/providers/ihela/test/withdrawal",
        json={
            "debit_account": "76001002",
            "debit_account_holder": "John Doe",
            "amount": 3000,
            "description": "Test transfert externe Paylink",
            "external_reference": "PAYLINK-TEST-001",
            "pin_code": "1234",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["transport"] == "bridge"
    assert payload["bridge_url"] == "https://bridge.example.test/ihela/transfer"
    assert payload["response"]["response_data"]["reference"] == "IH-REF-001"
    assert calls == [
        (
            "/ihela/transfer",
            {
                "debit_account": "76001002",
                "debit_account_holder": "John Doe",
                "amount": 3000,
                "description": "Test transfert externe Paylink",
                "external_reference": "PAYLINK-TEST-001",
                "pin_code": "1234",
            },
        )
    ]


def test_ihela_test_transaction_status_requires_admin_or_agent(monkeypatch):
    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "https://bridge.example.test")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "bridge-key")

    client = _build_test_client(role="client")
    response = client.post(
        "/providers/ihela/test/transaction-status",
        json={"reference": "IH-REF-001"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Acces refuse"


def test_ihela_test_withdrawal_reports_missing_direct_config(monkeypatch):
    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "")

    client = _build_test_client(role="agent")
    response = client.post(
        "/providers/ihela/test/withdrawal",
        json={
            "debit_account": "76001002",
            "debit_account_holder": "John Doe",
            "amount": 3000,
            "description": "Test transfert externe Paylink",
            "external_reference": "PAYLINK-TEST-001",
            "pin_code": "1234",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "IHELA_API_BASE_URL manquant"

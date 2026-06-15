from types import SimpleNamespace

import pytest
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


def test_ihela_test_withdrawal_allows_client_role(monkeypatch):
    async def fake_bridge_post(path, payload):
        return 200, {
            "response_data": {
                "reference": "IH-CLIENT-001",
            },
        }

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "https://bridge.example.test")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "bridge-key")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_WITHDRAWAL_PATH", "/ihela/transfer")
    monkeypatch.setattr(ihela, "_bridge_post", fake_bridge_post)

    client = _build_test_client(role="client")
    response = client.post(
        "/providers/ihela/test/withdrawal",
        json={
            "debit_account": "76001002",
            "debit_account_holder": "John Doe",
            "amount": 3000,
            "description": "Test transfert externe Paylink",
            "external_reference": "PAYLINK-TEST-CLIENT",
            "pin_code": "1234",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["transport"] == "bridge"
    assert payload["response"]["response_data"]["reference"] == "IH-CLIENT-001"


def test_ihela_test_transaction_status_allows_client_role(monkeypatch):
    calls = []

    async def fake_bridge_post(path, payload):
        calls.append((path, payload))
        return 200, {"response_data": {"status": "SUCCESS"}}

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "https://bridge.example.test")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "bridge-key")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_STATUS_PATH", "/ihela/transaction-status")
    monkeypatch.setattr(ihela, "_bridge_post", fake_bridge_post)

    client = _build_test_client(role="client")
    response = client.post(
        "/providers/ihela/test/transaction-status",
        json={"reference": "IH-REF-001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["transport"] == "bridge"
    assert payload["response"]["response_data"]["status"] == "SUCCESS"
    assert calls == [("/ihela/transaction-status", {"reference": "IH-REF-001"})]


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


def test_ihela_oauth_debug_returns_resolved_urls_without_secrets(monkeypatch):
    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://api.ihela.bi")
    monkeypatch.setattr(settings, "IHELA_AUTH_TOKEN_MODE", "client_credentials")
    monkeypatch.setattr(settings, "IHELA_OAUTH_TOKEN_PATH", "/testenv/oAuth2/token/")
    monkeypatch.setattr(settings, "IHELA_BANKING_API_PREFIX", "/testenv/ihela/api/v1")
    monkeypatch.setattr(settings, "IHELA_SEND_PATH", "make-withdrawal")
    monkeypatch.setattr(settings, "IHELA_STATUS_PATH", "transaction-status")
    monkeypatch.setattr(settings, "IHELA_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "IHELA_OAUTH_CLIENT_SECRET", "client-secret")

    client = _build_test_client(role="admin")
    response = client.get("/providers/ihela/test/oauth-debug")

    assert response.status_code == 200
    payload = response.json()
    assert payload["transport"] == "direct"
    assert payload["ihela_api_base_url"] == "https://api.ihela.bi"
    assert payload["auth_token_mode"] == "client_credentials"
    assert payload["token_urls"] == ["https://api.ihela.bi/testenv/oAuth2/token/"]
    assert payload["withdrawal_path"] == "make-withdrawal"
    assert payload["withdrawal_url"] == "https://api.ihela.bi/testenv/ihela/api/v1/make-withdrawal/"
    assert payload["has_oauth_client_id"] is True
    assert payload["has_oauth_client_secret"] is True
    assert "client-secret" not in response.text


def test_ihela_test_withdrawal_retries_testenv_prefix_after_404(monkeypatch):
    calls = []

    async def fake_fetch_oauth_token():
        return {"access_token": "token-123", "token_type": "Bearer"}

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.content = body.encode("utf-8")
            self.text = body

        def json(self):
            return {"response_data": {"reference": "IH-REF-RETRY"}}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url == "https://api.ihela.bi/ihela/api/v1/make-withdrawal/":
                return FakeResponse(404, "Page not found")
            return FakeResponse(200, '{"response_data":{"reference":"IH-REF-RETRY"}}')

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://api.ihela.bi")
    monkeypatch.setattr(settings, "IHELA_AUTH_TOKEN_MODE", "client_credentials")
    monkeypatch.setattr(settings, "IHELA_OAUTH_TOKEN_PATH", "/testenv/oAuth2/token/")
    monkeypatch.setattr(settings, "IHELA_BANKING_API_PREFIX", "/ihela/api/v1")
    monkeypatch.setattr(settings, "IHELA_SEND_PATH", "make-withdrawal")
    monkeypatch.setattr(ihela, "_ihela_fetch_oauth_token", fake_fetch_oauth_token)
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

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
    assert payload["attempted_urls"] == [
        "https://api.ihela.bi/ihela/api/v1/make-withdrawal/",
        "https://api.ihela.bi/testenv/ihela/api/v1/make-withdrawal/",
    ]
    assert calls[1][0] == "https://api.ihela.bi/testenv/ihela/api/v1/make-withdrawal/"


def test_ihela_test_account_lookup_uses_direct_get(monkeypatch):
    calls = []

    async def fake_fetch_oauth_token():
        return {"access_token": "token-lookup", "token_type": "Bearer"}

    class FakeResponse:
        status_code = 200
        content = b'{"account_name":"Demo Client"}'
        text = '{"account_name":"Demo Client"}'

        def json(self):
            return {"account_name": "Demo Client"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://api.ihela.bi")
    monkeypatch.setattr(settings, "IHELA_ACCOUNT_LOOKUP_PATH", "/testenv/api/v2/bank/MF1-0001/account/lookup")
    monkeypatch.setattr(ihela, "_ihela_fetch_oauth_token", fake_fetch_oauth_token)
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    client = _build_test_client(role="admin")
    response = client.post(
        "/providers/ihela/test/account-lookup",
        json={"account_number": "16-01"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["transport"] == "direct"
    assert payload["attempted_urls"] == [
        "https://api.ihela.bi/testenv/api/v2/bank/MF1-0001/account/lookup/"
    ]
    assert payload["response"]["account_name"] == "Demo Client"
    assert calls == [
        (
            "https://api.ihela.bi/testenv/api/v2/bank/MF1-0001/account/lookup/",
            {
                "headers": {
                    "Authorization": "Bearer token-lookup",
                    "Accept": "application/json",
                },
                "params": {"account_number": "16-01"},
            },
        )
    ]


def test_ihela_test_account_lookup_allows_client_role(monkeypatch):
    async def fake_fetch_oauth_token():
        return {"access_token": "token-client", "token_type": "Bearer"}

    class FakeResponse:
        status_code = 200
        content = b'{"account_name":"Client Demo"}'
        text = '{"account_name":"Client Demo"}'

        def json(self):
            return {"account_name": "Client Demo"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://api.ihela.bi")
    monkeypatch.setattr(settings, "IHELA_ACCOUNT_LOOKUP_PATH", "/testenv/api/v2/bank/MF1-0001/account/lookup")
    monkeypatch.setattr(ihela, "_ihela_fetch_oauth_token", fake_fetch_oauth_token)
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    client = _build_test_client(role="client")
    response = client.post(
        "/providers/ihela/test/account-lookup",
        json={"account_number": "16-01"},
    )

    assert response.status_code == 200
    assert response.json()["response"]["account_name"] == "Client Demo"


def test_ihela_test_bank_cashout_uses_direct_get_for_client_role(monkeypatch):
    calls = []

    async def fake_fetch_oauth_token():
        return {"access_token": "token-cashout", "token_type": "Bearer"}

    class FakeResponse:
        status_code = 200
        content = b'{"items":[]}'
        text = '{"items":[]}'

        def json(self):
            return {"items": []}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://api.ihela.bi")
    monkeypatch.setattr(settings, "IHELA_BANK_CASHOUT_PATH", "/testenv/api/v2/payments/bank/cashout")
    monkeypatch.setattr(ihela, "_ihela_fetch_oauth_token", fake_fetch_oauth_token)
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    client = _build_test_client(role="client")
    response = client.get("/providers/ihela/test/bank-cashout")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["transport"] == "direct"
    assert payload["attempted_urls"] == [
        "https://api.ihela.bi/testenv/api/v2/payments/bank/cashout/"
    ]
    assert payload["response"]["items"] == []
    assert calls == [
        (
            "https://api.ihela.bi/testenv/api/v2/payments/bank/cashout/",
            {
                "headers": {
                    "Authorization": "Bearer token-cashout",
                    "Accept": "application/json",
                },
            },
        )
    ]


def test_ihela_test_bank_cashin_uses_direct_get_for_client_role(monkeypatch):
    calls = []

    async def fake_fetch_oauth_token():
        return {"access_token": "token-cashin", "token_type": "Bearer"}

    class FakeResponse:
        status_code = 200
        content = b'{"items":[]}'
        text = '{"items":[]}'

        def json(self):
            return {"items": []}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://api.ihela.bi")
    monkeypatch.setattr(settings, "IHELA_BANK_CASHIN_PATH", "/testenv/api/v2/payments/bank/cashin")
    monkeypatch.setattr(ihela, "_ihela_fetch_oauth_token", fake_fetch_oauth_token)
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    client = _build_test_client(role="client")
    response = client.get("/providers/ihela/test/bank-cashin")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["transport"] == "direct"
    assert payload["attempted_urls"] == [
        "https://api.ihela.bi/testenv/api/v2/payments/bank/cashin/"
    ]
    assert payload["response"]["items"] == []
    assert calls == [
        (
            "https://api.ihela.bi/testenv/api/v2/payments/bank/cashin/",
            {
                "headers": {
                    "Authorization": "Bearer token-cashin",
                    "Accept": "application/json",
                },
            },
        )
    ]


def test_ihela_test_mobile_cashout_uses_direct_post_for_client_role(monkeypatch):
    calls = []

    async def fake_fetch_oauth_token():
        return {"access_token": "token-mobile-cashout", "token_type": "Bearer"}

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self.content = body.encode("utf-8")
            self.text = body

        def json(self):
            if self.status_code == 404:
                return {"detail": "Not found"}
            return {"reference": "TXN_2026_001", "status": "PENDING"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url in {
                "https://api.ihela.bi/testenv/api/v2/payments/mobile/cashout/",
                "https://api.ihela.bi/testenv/api/v2/payments/cashout/",
            }:
                return FakeResponse(404, '{"detail":"Not found"}')
            return FakeResponse(201, '{"reference":"TXN_2026_001","status":"PENDING"}')

    monkeypatch.setattr(settings, "IHELA_BRIDGE_BASE_URL", "")
    monkeypatch.setattr(settings, "IHELA_BRIDGE_API_KEY", "")
    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://api.ihela.bi")
    monkeypatch.setattr(settings, "IHELA_MOBILE_CASHOUT_PATH", "/testenv/api/v2/payments/cashout")
    monkeypatch.setattr(ihela, "_ihela_fetch_oauth_token", fake_fetch_oauth_token)
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    client = _build_test_client(role="client")
    response = client.post(
        "/providers/ihela/test/mobile-cashout",
        json={
            "endpoint_path": "/testenv/api/v2/payments/mobile/cashin",
            "amount": 5000,
            "recipient": "67225225",
            "provider": "LUMICASH",
            "merchant_reference": "TXN_2026_001",
            "description": "Transfert de 5000 BIF vers le numero 67225225",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["http_status"] == 201
    assert payload["attempted_urls"] == [
        "https://api.ihela.bi/testenv/api/v2/payments/mobile/cashin/",
    ]
    assert payload["response"]["status"] == "PENDING"
    assert calls[0] == (
        "https://api.ihela.bi/testenv/api/v2/payments/bank/cashin/",
        {
            "headers": {
                "Authorization": "Bearer token-mobile-cashout",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "json": {
                "amount": 5000,
                "recipient": "67225225",
                "provider": "LUMICASH",
                "merchant_reference": "TXN_2026_001",
                "description": "Transfert de 5000 BIF vers le numero 67225225",
            },
        },
    )


@pytest.mark.anyio
async def test_ihela_fetch_oauth_token_client_credentials_payload(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        text = '{"access_token":"token-123"}'
        content = b'{"access_token":"token-123"}'

        def json(self):
            return {"access_token": "token-123", "token_type": "Bearer"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://ihela.example.test")
    monkeypatch.setattr(settings, "IHELA_AUTH_TOKEN_MODE", "client_credentials")
    monkeypatch.setattr(settings, "IHELA_OAUTH_TOKEN_PATH", "")
    monkeypatch.setattr(settings, "IHELA_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "IHELA_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    token = await ihela._ihela_fetch_oauth_token()

    assert token["access_token"] == "token-123"
    assert calls[0][0] == "https://ihela.example.test/oAuth2/token/"
    assert calls[0][1]["files"] == {"grant_type": (None, "client_credentials")}
    assert calls[0][1]["headers"]["Authorization"].startswith("Basic ")


@pytest.mark.anyio
async def test_ihela_fetch_oauth_token_password_mode_uses_auth_token_default_path(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        text = '{"access":"token-456"}'
        content = b'{"access":"token-456"}'

        def json(self):
            return {"access": "token-456"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://ihela.example.test")
    monkeypatch.setattr(settings, "IHELA_AUTH_TOKEN_MODE", "password")
    monkeypatch.setattr(settings, "IHELA_OAUTH_TOKEN_PATH", "")
    monkeypatch.setattr(settings, "IHELA_AUTH_USERNAME", "merchant-user")
    monkeypatch.setattr(settings, "IHELA_AUTH_PASSWORD", "merchant-pass")
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    token = await ihela._ihela_fetch_oauth_token()

    assert token["access_token"] == "token-456"
    assert calls[0][0] == "https://ihela.example.test/ihela/api/v1/auth-token/"
    assert calls[0][1]["json"] == {
        "username": "merchant-user",
        "password": "merchant-pass",
    }
    assert calls[0][1]["headers"]["Content-Type"] == "application/json"


@pytest.mark.anyio
async def test_ihela_fetch_oauth_token_falls_back_to_password_on_unsupported_grant(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.text = body
            self.content = body.encode("utf-8")

        def json(self):
            if self.status_code >= 400:
                return {"error": "unsupported_grant_type"}
            return {"access_token": "fallback-token"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if len(calls) == 1:
                return FakeResponse(400, '{"error":"unsupported_grant_type"}')
            return FakeResponse(200, '{"access_token":"fallback-token"}')

    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://ihela.example.test")
    monkeypatch.setattr(settings, "IHELA_AUTH_TOKEN_MODE", "client_credentials")
    monkeypatch.setattr(settings, "IHELA_OAUTH_TOKEN_PATH", "")
    monkeypatch.setattr(settings, "IHELA_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "IHELA_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "IHELA_AUTH_USERNAME", "merchant-user")
    monkeypatch.setattr(settings, "IHELA_AUTH_PASSWORD", "merchant-pass")
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    token = await ihela._ihela_fetch_oauth_token()

    assert token["access_token"] == "fallback-token"
    assert calls[0][0] == "https://ihela.example.test/oAuth2/token/"
    assert calls[0][1]["files"] == {"grant_type": (None, "client_credentials")}
    assert calls[1][0] == "https://ihela.example.test/ihela/api/v1/auth-token/"
    assert calls[1][1]["json"] == {
        "username": "merchant-user",
        "password": "merchant-pass",
    }


@pytest.mark.anyio
async def test_ihela_fetch_oauth_token_password_mode_retries_without_ihela_prefix_on_404(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self.text = body
            self.content = body.encode("utf-8")

        def json(self):
            return {"access_token": "token-without-prefix"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/ihela/api/v1/auth-token/"):
                return FakeResponse(404, "Page not found at /ihela/api/v1/auth-token/")
            return FakeResponse(200, '{"access_token":"token-without-prefix"}')

    monkeypatch.setattr(settings, "IHELA_API_BASE_URL", "https://ihela.example.test")
    monkeypatch.setattr(settings, "IHELA_AUTH_TOKEN_MODE", "password")
    monkeypatch.setattr(settings, "IHELA_OAUTH_TOKEN_PATH", "")
    monkeypatch.setattr(settings, "IHELA_AUTH_USERNAME", "merchant-user")
    monkeypatch.setattr(settings, "IHELA_AUTH_PASSWORD", "merchant-pass")
    monkeypatch.setattr(ihela.httpx, "AsyncClient", FakeAsyncClient)

    token = await ihela._ihela_fetch_oauth_token()

    assert token["access_token"] == "token-without-prefix"
    assert calls[0][0] == "https://ihela.example.test/ihela/api/v1/auth-token/"
    assert calls[1][0] == "https://ihela.example.test/api/v1/auth-token/"


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param

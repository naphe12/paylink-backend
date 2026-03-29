from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.escrow.escrow_audit_export import router as escrow_audit_export_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(escrow_audit_export_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id="admin-1", role="admin")

    async def override_get_db():
        return db

    async def override_get_current_user_db():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user_db
    return TestClient(app)


def test_escrow_audit_export_csv_http(monkeypatch):
    class _FakeRows:
        def fetchall(self):
            return [
                (
                    "order-1",
                    "PAID_OUT",
                    "user-1",
                    "Deposant A",
                    "user-1",
                    "Deposant A",
                    "operator-1",
                    "Operateur A",
                    "operator-1",
                    "Operateur A",
                    100,
                    100,
                    99,
                    99,
                    290000,
                    290000,
                    10,
                    "POLYGON",
                    "0xabc",
                    "0xhash",
                    "Lumicash",
                    "Benef A",
                    "+25761234567",
                    "Benef A",
                    "+25761234567",
                    "REF-1",
                    "2026-03-29T10:00:00Z",
                    "2026-03-29T10:10:00Z",
                    "2026-03-29T10:20:00Z",
                    "2026-03-29T10:30:00Z",
                    "2026-03-29T09:50:00Z",
                    "2026-03-29T10:30:00Z",
                )
            ]

    async def fake_fetch_rows(db, **kwargs):
        assert kwargs["limit"] == 5000
        return _FakeRows()

    from app.routers.escrow import escrow_audit_export as module

    monkeypatch.setattr(module, "fetch_escrow_order_rows", fake_fetch_rows)
    client = _build_test_client()

    response = client.get("/backoffice/escrow/audit/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "id,status,user_id,user_name" in body
    assert "order-1" in body
    assert "Deposant A" in body
    assert "Operateur A" in body

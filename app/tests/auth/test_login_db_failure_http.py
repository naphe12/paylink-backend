from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.routers.auth.auth import router as auth_router


class _DbFailure:
    async def scalar(self, *_args, **_kwargs):
        raise SQLAlchemyError("db unavailable")


def test_login_returns_503_when_database_is_unavailable():
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")

    async def override_get_db():
        return _DbFailure()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        data={"username": "client@example.com", "password": "secret"},
    )

    assert response.status_code == 503
    assert "indisponible" in response.json()["detail"].lower()

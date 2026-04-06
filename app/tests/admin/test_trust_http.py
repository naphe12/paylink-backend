from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db
from app.routers.trust import router as trust_router


class _FakeDb:
    pass


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(trust_router)
    db = _FakeDb()
    current_user = SimpleNamespace(user_id=uuid4(), role="client", email="client@example.com")
    current_admin = SimpleNamespace(user_id=uuid4(), role="admin", email="admin@example.com")

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


def test_get_my_trust_profile_and_admin_recompute(monkeypatch):
    from app.routers import trust as trust_module

    user_id = uuid4()

    async def fake_get_trust_profile(db, *, user_id):
        return {
            "profile": {
                "user_id": str(user_id),
                "trust_score": 68,
                "trust_level": "trusted",
                "successful_payment_requests": 4,
                "successful_p2p_trades": 0,
                "dispute_count": 0,
                "failed_obligation_count": 0,
                "chargeback_like_count": 0,
                "kyc_verified": True,
                "account_age_days": 210,
                "last_computed_at": "2026-04-05T10:00:00Z",
                "metadata": {},
                "created_at": "2026-04-05T10:00:00Z",
                "updated_at": "2026-04-05T10:00:00Z",
                "badges": [
                    {
                        "badge_code": "kyc_verified",
                        "name": "KYC verifie",
                        "description": "Identite verifiee avec succes.",
                        "granted_at": "2026-04-05T10:00:00Z",
                    }
                ],
            },
            "events": [
                {
                    "event_id": str(uuid4()),
                    "user_id": str(user_id),
                    "source_type": "recompute",
                    "source_id": None,
                    "score_delta": 12,
                    "reason_code": "profile_recomputed",
                    "metadata": {},
                    "created_at": "2026-04-05T10:00:00Z",
                }
            ],
        }

    async def fake_recompute_trust_profile(db, *, user_id):
        return {
            "user_id": str(user_id),
            "trust_score": 72,
            "trust_level": "trusted",
            "successful_payment_requests": 5,
            "successful_p2p_trades": 0,
            "dispute_count": 0,
            "failed_obligation_count": 0,
            "chargeback_like_count": 0,
            "kyc_verified": True,
            "account_age_days": 240,
            "last_computed_at": "2026-04-05T10:10:00Z",
            "metadata": {},
            "created_at": "2026-04-05T10:00:00Z",
            "updated_at": "2026-04-05T10:10:00Z",
            "badges": [],
        }

    monkeypatch.setattr(trust_module, "get_trust_profile", fake_get_trust_profile)
    monkeypatch.setattr(trust_module, "recompute_trust_profile", fake_recompute_trust_profile)

    client = _build_test_client()
    client.app.dependency_overrides[get_current_user_db] = lambda: SimpleNamespace(user_id=user_id, role="client")

    me_response = client.get("/trust/me")
    assert me_response.status_code == 200
    assert me_response.json()["profile"]["trust_score"] == 68

    admin_response = client.post(f"/admin/trust/recompute/{user_id}")
    assert admin_response.status_code == 200
    assert admin_response.json()["profile"]["trust_score"] == 72

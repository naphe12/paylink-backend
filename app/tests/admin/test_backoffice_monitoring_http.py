from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.routers.backoffice_monitoring import router as backoffice_monitoring_router


class _FakeMappingsResult:
    def __init__(self, rows):
        self._rows = rows

    def one(self):
        return self._rows[0]

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    async def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM escrow.webhook_logs" in sql:
            return _FakeMappingsResult(
                [
                    {
                        "total": 15,
                        "success": 9,
                        "failed": 2,
                        "duplicate": 0,
                        "success_retry": 1,
                        "failed_retry": 3,
                    }
                ]
            )
        if "FROM escrow.webhook_retries" in sql:
            return _FakeMappingsResult([{"c": 12}])
        if "FROM (" in sql and "paylink.ledger_entries" in sql:
            return _FakeMappingsResult([{"c": 1}])
        if "FROM paylink.idempotency_keys" in sql:
            return _FakeMappingsResult(
                [
                    {
                        "total_keys": 120,
                        "pending_keys": 55,
                        "keys_window": 30,
                    }
                ]
            )
        if "FROM paylink.external_transfers" in sql:
            return _FakeMappingsResult(
                [
                    {
                        "total": 100,
                        "pending": 27,
                        "approved": 10,
                        "succeeded": 58,
                        "failed": 5,
                    }
                ]
            )
        raise AssertionError(f"Unexpected SQL in fake db: {sql}")


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(backoffice_monitoring_router)
    fake_db = _FakeDb()

    async def override_get_db():
        return fake_db

    async def override_get_current_user_db():
        return SimpleNamespace(
            user_id=uuid4(),
            role="admin",
            full_name="Admin Ops",
            email="ops@example.com",
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_db] = override_get_current_user_db
    return TestClient(app)


def test_ops_metrics_exposes_business_sla_blocks(monkeypatch):
    from app.routers import backoffice_monitoring as module

    async def fake_table_exists(db, full_name):
        if full_name == "paylink.request_metrics":
            return False
        if full_name == "escrow.webhook_retries":
            return True
        raise AssertionError(f"Unexpected table lookup: {full_name}")

    async def fake_fetch_operator_workflow_summary(db, *, current_user_id, current_owner_label):
        assert current_owner_label == "Admin Ops"
        return {
            "all": 22,
            "mine": 5,
            "team": 17,
            "unassigned": 4,
            "blocked_only": 16,
            "needs_follow_up": 8,
            "watching": 1,
            "resolved": 2,
            "overdue_follow_up": 11,
        }

    async def fake_fetch_operator_urgency_items(db):
        return [
            {"kind": "escrow", "priority": "critical", "stale": True},
            {"kind": "escrow", "priority": "warning", "stale": False},
            {"kind": "payment_intent", "priority": "critical", "stale": True},
            {"kind": "p2p_dispute", "priority": "warning", "stale": True},
            {"kind": "payment_intent", "priority": "warning", "stale": True},
            {"kind": "p2p_dispute", "priority": "warning", "stale": True},
        ]

    monkeypatch.setattr(module, "_table_exists", fake_table_exists)
    monkeypatch.setattr(module, "fetch_operator_workflow_summary", fake_fetch_operator_workflow_summary)
    monkeypatch.setattr(module, "fetch_operator_urgency_items", fake_fetch_operator_urgency_items)

    client = _build_test_client()
    response = client.get("/backoffice/monitoring/ops-metrics?window_hours=24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "CRITICAL"
    assert payload["ops_workflow"]["overdue_follow_up"] == 11
    assert payload["ops_workflow"]["blocked_only"] == 16
    assert payload["ops_urgencies"]["total"] == 6
    assert payload["ops_urgencies"]["stale"] == 5
    assert payload["ops_urgencies"]["critical"] == 2
    assert payload["ops_urgencies"]["by_kind"]["escrow"] == 2
    assert payload["ops_urgencies"]["by_kind"]["payment_intent"] == 2
    assert payload["ops_urgencies"]["by_kind"]["p2p_dispute"] == 2
    assert isinstance(payload["ops_urgencies"]["sla_trend"], list)
    assert payload["ops_urgencies"]["sla_trend"]
    assert all("date" in point for point in payload["ops_urgencies"]["sla_trend"])
    assert any(alert["code"] == "ops_overdue_follow_up_critical" for alert in payload["alerts"])
    assert any(alert["code"] == "ops_blocked_high" for alert in payload["alerts"])
    assert any(alert["code"] == "ops_stale_urgencies_high" for alert in payload["alerts"])
    assert any("Urgences OPS" in action for action in payload["recommended_actions"])
    assert any(item["route"] == "/dashboard/admin/ledger/unbalanced-journals" for item in payload["recommended_runbooks"])
    assert any(item["route"] == "/dashboard/admin/ops-urgencies" for item in payload["recommended_runbooks"])


def test_export_ops_metrics_csv_includes_business_sla_rows(monkeypatch):
    from app.routers import backoffice_monitoring as module

    async def fake_ops_metrics(*, window_hours, path_prefix, db, user):
        return {
            "window_hours": window_hours,
            "status": "WARN",
            "alerts": [{"code": "ops_stale_urgencies_high"}],
            "recommended_actions": ["Passer par la file 'Urgences OPS'."],
            "recommended_runbooks": [
                {
                    "code": "ops_stale_urgencies_high",
                    "title": "Vider la file Urgences OPS",
                    "route": "/dashboard/admin/ops-urgencies",
                    "rationale": "Des urgences sont stale.",
                }
            ],
            "api": {"path_prefix": path_prefix, "total_requests": None, "errors_4xx": None, "errors_5xx": None, "error_rate_percent": None, "latency_p50_ms": None, "latency_p95_ms": None},
            "webhooks": {"total": 0, "failed": 0, "failed_retry": 0, "retry_queue_size": 0},
            "ledger": {"unbalanced_journals": 0},
            "idempotency": {"total_keys": 0, "pending_keys": 0, "keys_window": 0},
            "external_transfers": {"total": 0, "pending": 0, "approved": 0, "succeeded": 0, "failed": 0},
            "ops_workflow": {"all": 9, "unassigned": 2, "blocked_only": 3, "overdue_follow_up": 4},
            "ops_urgencies": {
                "total": 7,
                "stale": 5,
                "critical": 2,
                "by_kind": {"escrow": 3, "p2p_dispute": 2, "payment_intent": 2},
                "sla_trend": [
                    {
                        "date": "2026-04-03",
                        "total": 7,
                        "stale": 5,
                        "critical": 2,
                        "escrow": 3,
                        "p2p_dispute": 2,
                        "payment_intent": 2,
                    }
                ],
            },
        }

    monkeypatch.setattr(module, "ops_metrics", fake_ops_metrics)

    client = _build_test_client()
    response = client.get("/backoffice/monitoring/ops-metrics/export.csv?window_hours=24")

    assert response.status_code == 200
    body = response.text
    assert "ops_workflow.overdue_follow_up,4" in body
    assert "ops_workflow.blocked_only,3" in body
    assert "ops_urgencies.stale,5" in body
    assert "ops_urgencies.by_kind.escrow,3" in body
    assert "ops_urgencies.sla_trend.2026-04-03.total,7" in body
    assert "recommended_runbooks.ops_stale_urgencies_high.route,/dashboard/admin/ops-urgencies" in body

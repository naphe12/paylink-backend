import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users

router = APIRouter(prefix="/backoffice/monitoring", tags=["Backoffice - Monitoring"])


def _require_monitoring_role(user: Users) -> None:
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")


async def _table_exists(db: AsyncSession, full_name: str) -> bool:
    row = await db.execute(
        text("SELECT to_regclass(:name) IS NOT NULL AS ok"),
        {"name": full_name},
    )
    return bool((row.mappings().first() or {}).get("ok"))


@router.get("/idempotency-health")
async def idempotency_health(
    retention_hours: int = Query(
        default=max(1, int(getattr(settings, "IDEMPOTENCY_RETENTION_HOURS", 72) or 72)),
        ge=1,
        le=24 * 90,
        description="Fenetre d'expiration estimee, en heures.",
    ),
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_monitoring_role(user)

    stats = await db.execute(
        text(
            """
            SELECT
              COUNT(*)::int AS total_keys,
              COUNT(*) FILTER (
                WHERE created_at < (NOW() - make_interval(hours => :retention_hours))
              )::int AS estimated_expired_keys,
              MIN(created_at) AS oldest_key_at,
              MAX(created_at) AS newest_key_at
            FROM paylink.idempotency_keys
            """
        ),
        {"retention_hours": retention_hours},
    )
    row = stats.mappings().one()
    total_keys = int(row["total_keys"] or 0)
    estimated_expired_keys = int(row["estimated_expired_keys"] or 0)

    return {
        "retention_hours": retention_hours,
        "total_keys": total_keys,
        "estimated_expired_keys": estimated_expired_keys,
        "active_keys": max(0, total_keys - estimated_expired_keys),
        "oldest_key_at": row["oldest_key_at"].isoformat() if row["oldest_key_at"] else None,
        "newest_key_at": row["newest_key_at"].isoformat() if row["newest_key_at"] else None,
    }


@router.get("/idempotency-scopes")
async def idempotency_scopes(
    retention_hours: int = Query(
        default=max(1, int(getattr(settings, "IDEMPOTENCY_RETENTION_HOURS", 72) or 72)),
        ge=1,
        le=24 * 90,
    ),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_monitoring_role(user)

    rows = await db.execute(
        text(
            """
            SELECT
              split_part(client_key, ':', 1) AS scope,
              COUNT(*)::int AS total_keys,
              COUNT(*) FILTER (WHERE response_payload IS NOT NULL)::int AS completed_keys,
              COUNT(*) FILTER (WHERE response_payload IS NULL)::int AS pending_keys,
              COUNT(*) FILTER (
                WHERE created_at < (NOW() - make_interval(hours => :retention_hours))
              )::int AS estimated_expired_keys,
              COUNT(*) FILTER (WHERE created_at >= NOW() - interval '24 hours')::int AS keys_24h,
              MIN(created_at) AS oldest_key_at,
              MAX(created_at) AS newest_key_at
            FROM paylink.idempotency_keys
            GROUP BY split_part(client_key, ':', 1)
            ORDER BY total_keys DESC, newest_key_at DESC
            LIMIT :limit
            """
        ),
        {"retention_hours": retention_hours, "limit": limit},
    )

    items = []
    for row in rows.mappings().all():
        items.append(
            {
                "scope": row["scope"] or "unknown",
                "total_keys": int(row["total_keys"] or 0),
                "completed_keys": int(row["completed_keys"] or 0),
                "pending_keys": int(row["pending_keys"] or 0),
                "estimated_expired_keys": int(row["estimated_expired_keys"] or 0),
                "keys_24h": int(row["keys_24h"] or 0),
                "oldest_key_at": row["oldest_key_at"].isoformat() if row["oldest_key_at"] else None,
                "newest_key_at": row["newest_key_at"].isoformat() if row["newest_key_at"] else None,
            }
        )

    return {
        "retention_hours": retention_hours,
        "count": len(items),
        "items": items,
    }

@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_monitoring_role(user)
    # volumes par statut + webhooks failed (24h) + unbalanced journals
    stats = await db.execute(text("""
      SELECT status, COUNT(*)::int AS count
      FROM escrow.orders
      GROUP BY status
    """))
    by_status = [dict(r._mapping) for r in stats.fetchall()]

    wh = await db.execute(text("""
      SELECT status, COUNT(*)::int AS count
      FROM escrow.webhook_logs
      WHERE created_at >= now() - interval '24 hours'
      GROUP BY status
    """))
    webhook = [dict(r._mapping) for r in wh.fetchall()]

    bad = await db.execute(text("""
      SELECT COUNT(*)::int FROM (
        SELECT journal_id
        FROM paylink.ledger_entries
        GROUP BY journal_id
        HAVING SUM(CASE WHEN direction='DEBIT' THEN amount ELSE 0 END)
            <> SUM(CASE WHEN direction='CREDIT' THEN amount ELSE 0 END)
      ) t
    """))

    return {
        "orders_by_status": by_status,
        "webhooks_24h": webhook,
        "unbalanced_journals": bad.scalar_one(),
    }


@router.get("/unbalanced-journals")
async def list_unbalanced_journals(
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_monitoring_role(user)

    rows = await db.execute(
        text(
            """
            SELECT
              lj.journal_id,
              lj.tx_id,
              lj.description,
              lj.occurred_at,
              COUNT(le.entry_id)::int AS entry_count,
              SUM(CASE WHEN LOWER(le.direction::text) = 'debit'  THEN le.amount ELSE 0 END) AS total_debit,
              SUM(CASE WHEN LOWER(le.direction::text) = 'credit' THEN le.amount ELSE 0 END) AS total_credit,
              SUM(CASE WHEN LOWER(le.direction::text) = 'debit'  THEN le.amount ELSE 0 END)
              - SUM(CASE WHEN LOWER(le.direction::text) = 'credit' THEN le.amount ELSE 0 END) AS gap
            FROM paylink.ledger_entries le
            JOIN paylink.ledger_journal lj ON lj.journal_id = le.journal_id
            GROUP BY lj.journal_id, lj.tx_id, lj.description, lj.occurred_at
            HAVING
              SUM(CASE WHEN LOWER(le.direction::text) = 'debit'  THEN le.amount ELSE 0 END)
              <>
              SUM(CASE WHEN LOWER(le.direction::text) = 'credit' THEN le.amount ELSE 0 END)
            ORDER BY ABS(
              SUM(CASE WHEN LOWER(le.direction::text) = 'debit'  THEN le.amount ELSE 0 END)
              - SUM(CASE WHEN LOWER(le.direction::text) = 'credit' THEN le.amount ELSE 0 END)
            ) DESC,
            lj.occurred_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )

    items = []
    for row in rows.mappings().all():
        items.append(
            {
                "journal_id": str(row["journal_id"]),
                "tx_id": str(row["tx_id"]) if row["tx_id"] else None,
                "description": row["description"],
                "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
                "entry_count": int(row["entry_count"] or 0),
                "total_debit": float(row["total_debit"] or 0),
                "total_credit": float(row["total_credit"] or 0),
                "gap": float(row["gap"] or 0),
            }
        )

    return {"count": len(items), "items": items}


@router.get("/unbalanced-journals/{journal_id}/entries")
async def get_unbalanced_journal_entries(
    journal_id: str,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_monitoring_role(user)

    summary = await db.execute(
        text(
            """
            SELECT
              lj.journal_id,
              lj.tx_id,
              lj.description,
              lj.occurred_at,
              SUM(CASE WHEN LOWER(le.direction::text) = 'debit'  THEN le.amount ELSE 0 END) AS total_debit,
              SUM(CASE WHEN LOWER(le.direction::text) = 'credit' THEN le.amount ELSE 0 END) AS total_credit
            FROM paylink.ledger_journal lj
            JOIN paylink.ledger_entries le ON le.journal_id = lj.journal_id
            WHERE lj.journal_id = CAST(:journal_id AS uuid)
            GROUP BY lj.journal_id, lj.tx_id, lj.description, lj.occurred_at
            """
        ),
        {"journal_id": journal_id},
    )
    row = summary.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Journal introuvable")

    total_debit = row["total_debit"] or 0
    total_credit = row["total_credit"] or 0
    if total_debit == total_credit:
        return {
            "journal_id": str(row["journal_id"]),
            "status": "BALANCED",
            "message": "Le journal est deja equilibre.",
        }

    entries_q = await db.execute(
        text(
            """
            SELECT
              le.entry_id,
              le.account_id,
              la.code AS account_code,
              la.name AS account_name,
              le.direction,
              le.amount,
              le.currency_code
            FROM paylink.ledger_entries le
            LEFT JOIN paylink.ledger_accounts la ON la.account_id = le.account_id
            WHERE le.journal_id = CAST(:journal_id AS uuid)
            ORDER BY le.entry_id
            """
        ),
        {"journal_id": journal_id},
    )

    entries = []
    for entry in entries_q.mappings().all():
        entries.append(
            {
                "entry_id": str(entry["entry_id"]),
                "account_id": str(entry["account_id"]) if entry["account_id"] else None,
                "account_code": entry["account_code"],
                "account_name": entry["account_name"],
                "direction": str(entry["direction"]),
                "amount": float(entry["amount"] or 0),
                "currency_code": entry["currency_code"],
            }
        )

    return {
        "journal_id": str(row["journal_id"]),
        "tx_id": str(row["tx_id"]) if row["tx_id"] else None,
        "description": row["description"],
        "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
        "total_debit": float(total_debit),
        "total_credit": float(total_credit),
        "gap": float(total_debit - total_credit),
        "status": "UNBALANCED",
        "entries": entries,
    }


@router.get("/ops-metrics")
async def ops_metrics(
    window_hours: int = Query(24, ge=1, le=24 * 30),
    path_prefix: str | None = Query(
        default=None,
        description="Filtre optionnel des metrics API par prefixe de path (ex: /api/p2p).",
    ),
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_monitoring_role(user)

    api_errors_5xx = None
    api_latency_p95_ms = None
    api_note = "API request metrics not available yet (no request metrics table)."
    if await _table_exists(db, "paylink.request_metrics"):
        path_like = f"{path_prefix}%" if path_prefix else None
        api_sql = """
                SELECT
                  COUNT(*)::int AS total_requests,
                  COUNT(*) FILTER (WHERE status_code >= 400 AND status_code < 500)::int AS errors_4xx,
                  COUNT(*) FILTER (WHERE status_code >= 500 AND status_code < 600)::int AS errors_5xx,
                  percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms)::numeric AS latency_p50_ms,
                  percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric AS latency_p95_ms
                FROM paylink.request_metrics
                WHERE created_at >= NOW() - make_interval(hours => :window_hours)
        """
        api_params = {"window_hours": window_hours}
        if path_like:
            api_sql += "\n                  AND path LIKE :path_like"
            api_params["path_like"] = path_like
        api_q = await db.execute(
            text(api_sql),
            api_params,
        )
        api_row = api_q.mappings().one()
        total_requests = int(api_row["total_requests"] or 0)
        errors_4xx = int(api_row["errors_4xx"] or 0)
        api_errors_5xx = int(api_row["errors_5xx"] or 0)
        error_rate_percent = round(((errors_4xx + api_errors_5xx) / total_requests) * 100, 2) if total_requests > 0 else 0
        latency_p50_ms = float(api_row["latency_p50_ms"] or 0)
        api_latency_p95_ms = float(api_row["latency_p95_ms"] or 0)
        api_note = None
    else:
        total_requests = None
        errors_4xx = None
        error_rate_percent = None
        latency_p50_ms = None

    webhook_stats = await db.execute(
        text(
            """
            SELECT
              COUNT(*)::int AS total,
              COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'SUCCESS')::int AS success,
              COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'FAILED')::int AS failed,
              COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'DUPLICATE')::int AS duplicate,
              COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'SUCCESS_RETRY')::int AS success_retry,
              COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'FAILED_RETRY')::int AS failed_retry
            FROM escrow.webhook_logs
            WHERE created_at >= NOW() - make_interval(hours => :window_hours)
            """
        ),
        {"window_hours": window_hours},
    )
    webhook_row = webhook_stats.mappings().one()

    retries_queue = 0
    if await _table_exists(db, "escrow.webhook_retries"):
        retries_q = await db.execute(text("SELECT COUNT(*)::int AS c FROM escrow.webhook_retries"))
        retries_queue = int((retries_q.mappings().first() or {}).get("c") or 0)

    unbalanced_q = await db.execute(
        text(
            """
            SELECT COUNT(*)::int AS c FROM (
              SELECT journal_id
              FROM paylink.ledger_entries
              GROUP BY journal_id
              HAVING
                SUM(CASE WHEN LOWER(direction::text) = 'debit' THEN amount ELSE 0 END)
                <>
                SUM(CASE WHEN LOWER(direction::text) = 'credit' THEN amount ELSE 0 END)
            ) t
            """
        )
    )
    unbalanced = int((unbalanced_q.mappings().first() or {}).get("c") or 0)

    idem_q = await db.execute(
        text(
            """
            SELECT
              COUNT(*)::int AS total_keys,
              COUNT(*) FILTER (WHERE response_payload IS NULL)::int AS pending_keys,
              COUNT(*) FILTER (WHERE created_at >= NOW() - make_interval(hours => :window_hours))::int AS keys_window
            FROM paylink.idempotency_keys
            """
        ),
        {"window_hours": window_hours},
    )
    idem_row = idem_q.mappings().one()

    transfer_q = await db.execute(
        text(
            """
            SELECT
              COUNT(*)::int AS total,
              COUNT(*) FILTER (WHERE LOWER(COALESCE(status, '')) = 'pending')::int AS pending,
              COUNT(*) FILTER (WHERE LOWER(COALESCE(status, '')) = 'approved')::int AS approved,
              COUNT(*) FILTER (WHERE LOWER(COALESCE(status, '')) = 'succeeded')::int AS succeeded,
              COUNT(*) FILTER (WHERE LOWER(COALESCE(status, '')) = 'failed')::int AS failed
            FROM paylink.external_transfers
            """
        )
    )
    transfer_row = transfer_q.mappings().one()

    return {
        "window_hours": window_hours,
        "api": {
            "path_prefix": path_prefix,
            "total_requests": total_requests,
            "errors_4xx": errors_4xx,
            "errors_5xx": api_errors_5xx,
            "error_rate_percent": error_rate_percent,
            "latency_p50_ms": latency_p50_ms,
            "latency_p95_ms": api_latency_p95_ms,
            "note": api_note,
        },
        "webhooks": {
            "total": int(webhook_row["total"] or 0),
            "success": int(webhook_row["success"] or 0),
            "failed": int(webhook_row["failed"] or 0),
            "duplicate": int(webhook_row["duplicate"] or 0),
            "success_retry": int(webhook_row["success_retry"] or 0),
            "failed_retry": int(webhook_row["failed_retry"] or 0),
            "retry_queue_size": retries_queue,
        },
        "ledger": {
            "unbalanced_journals": unbalanced,
        },
        "idempotency": {
            "total_keys": int(idem_row["total_keys"] or 0),
            "pending_keys": int(idem_row["pending_keys"] or 0),
            "keys_window": int(idem_row["keys_window"] or 0),
        },
        "external_transfers": {
            "total": int(transfer_row["total"] or 0),
            "pending": int(transfer_row["pending"] or 0),
            "approved": int(transfer_row["approved"] or 0),
            "succeeded": int(transfer_row["succeeded"] or 0),
            "failed": int(transfer_row["failed"] or 0),
        },
    }


@router.get("/ops-metrics/export.csv")
async def export_ops_metrics_csv(
    window_hours: int = Query(24, ge=1, le=24 * 30),
    path_prefix: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    payload = await ops_metrics(
        window_hours=window_hours,
        path_prefix=path_prefix,
        db=db,
        user=user,
    )

    now_utc = datetime.now(timezone.utc).isoformat()
    api_block = payload.get("api") or {}
    webhook_block = payload.get("webhooks") or {}
    ledger_block = payload.get("ledger") or {}
    idem_block = payload.get("idempotency") or {}
    ext_block = payload.get("external_transfers") or {}

    rows = [
        ("generated_at_utc", now_utc),
        ("window_hours", payload.get("window_hours")),
        ("api.path_prefix", api_block.get("path_prefix")),
        ("api.total_requests", api_block.get("total_requests")),
        ("api.errors_4xx", api_block.get("errors_4xx")),
        ("api.errors_5xx", api_block.get("errors_5xx")),
        ("api.error_rate_percent", api_block.get("error_rate_percent")),
        ("api.latency_p50_ms", api_block.get("latency_p50_ms")),
        ("api.latency_p95_ms", api_block.get("latency_p95_ms")),
        ("webhooks.total", webhook_block.get("total")),
        ("webhooks.failed", webhook_block.get("failed")),
        ("webhooks.failed_retry", webhook_block.get("failed_retry")),
        ("webhooks.retry_queue_size", webhook_block.get("retry_queue_size")),
        ("ledger.unbalanced_journals", ledger_block.get("unbalanced_journals")),
        ("idempotency.total_keys", idem_block.get("total_keys")),
        ("idempotency.pending_keys", idem_block.get("pending_keys")),
        ("idempotency.keys_window", idem_block.get("keys_window")),
        ("external_transfers.total", ext_block.get("total")),
        ("external_transfers.pending", ext_block.get("pending")),
        ("external_transfers.approved", ext_block.get("approved")),
        ("external_transfers.succeeded", ext_block.get("succeeded")),
        ("external_transfers.failed", ext_block.get("failed")),
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "value"])
    for key, value in rows:
        writer.writerow([key, value])
    buf.seek(0)

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"ops_metrics_{suffix}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.services.operator_workflow_service import fetch_operator_urgency_items, fetch_operator_workflow_summary

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


def _compute_ops_status(
    *,
    unbalanced_journals: int,
    errors_5xx: int,
    error_rate_percent: float,
    latency_p95_ms: float,
    failed_retry: int,
    retry_queue_size: int,
) -> str:
    if (
        unbalanced_journals > 0
        or errors_5xx >= 10
        or error_rate_percent >= 10
        or latency_p95_ms >= 2000
        or failed_retry > 0
        or retry_queue_size >= 30
    ):
        return "CRITICAL"
    if (
        errors_5xx >= 1
        or error_rate_percent >= 3
        or latency_p95_ms >= 1000
        or retry_queue_size >= 10
    ):
        return "WARN"
    return "OK"


def _build_ops_alerts_and_actions(
    *,
    errors_5xx: int,
    error_rate_percent: float,
    latency_p95_ms: float,
    failed_retry: int,
    retry_queue_size: int,
    unbalanced_journals: int,
    pending_idempotency_keys: int,
    pending_external_transfers: int,
    overdue_follow_up: int,
    blocked_only: int,
    stale_urgencies: int,
) -> tuple[list[dict], list[str]]:
    alerts: list[dict] = []
    actions: list[str] = []

    def push_alert(level: str, code: str, title: str, detail: str) -> None:
        alerts.append({"level": level, "code": code, "title": title, "detail": detail})

    def push_action(message: str) -> None:
        if message not in actions:
            actions.append(message)

    if unbalanced_journals > 0:
        push_alert(
            "critical",
            "ledger_unbalanced",
            "Journaux ledger non equilibres",
            f"{unbalanced_journals} journal(x) avec debit != credit.",
        )
        push_action("Ouvrir 'Journaux non equilibres' et corriger les ecritures avant toute cloture OPS.")

    if errors_5xx >= 10:
        push_alert("critical", "api_5xx_spike", "Pic d'erreurs API 5xx", f"{errors_5xx} erreurs 5xx sur la fenetre analysee.")
        push_action("Verifier les erreurs API et les derniers deploys avant reprise normale.")
    elif errors_5xx >= 1:
        push_alert("warning", "api_5xx_present", "Erreurs API 5xx detectees", f"{errors_5xx} erreurs 5xx observees.")
        push_action("Examiner les erreurs API recentes pour confirmer l'absence de regression.")

    if error_rate_percent >= 10:
        push_alert("critical", "api_error_rate_high", "Taux d'erreur API tres eleve", f"Taux d'erreur a {error_rate_percent:.2f}%.")
        push_action("Verifier la sante des endpoints les plus sollicites et reduire le trafic si necessaire.")
    elif error_rate_percent >= 3:
        push_alert("warning", "api_error_rate_warn", "Taux d'erreur API en hausse", f"Taux d'erreur a {error_rate_percent:.2f}%.")

    if latency_p95_ms >= 2000:
        push_alert("critical", "api_latency_critical", "Latence API critique", f"p95 a {latency_p95_ms:.1f} ms.")
        push_action("Verifier la base et les endpoints lents; envisager de limiter les operations lourdes.")
    elif latency_p95_ms >= 1000:
        push_alert("warning", "api_latency_warn", "Latence API elevee", f"p95 a {latency_p95_ms:.1f} ms.")

    if failed_retry > 0:
        push_alert(
            "critical",
            "webhook_failed_retry",
            "Retries webhook en echec",
            f"{failed_retry} webhook(s) ont encore echoue apres retry.",
        )
        push_action("Ouvrir les logs webhooks et traiter les retries definitivement en echec.")

    if retry_queue_size >= 30:
        push_alert(
            "critical",
            "webhook_retry_queue_critical",
            "File de retry webhook saturee",
            f"{retry_queue_size} webhook(s) en file de retry.",
        )
        push_action("Traiter la file webhook en priorite pour eviter un retard de synchronisation.")
    elif retry_queue_size >= 10:
        push_alert(
            "warning",
            "webhook_retry_queue_warn",
            "File de retry webhook chargee",
            f"{retry_queue_size} webhook(s) en attente.",
        )

    if pending_idempotency_keys >= 50:
        push_alert(
            "warning",
            "idempotency_pending_high",
            "Cles d'idempotence en attente nombreuses",
            f"{pending_idempotency_keys} cle(s) sans payload de reponse.",
        )
        push_action("Verifier les traitements interrompus ou les reponses non persistees cote API.")

    if pending_external_transfers >= 25:
        push_alert(
            "warning",
            "external_transfers_pending_high",
            "Beaucoup de transferts externes pending",
            f"{pending_external_transfers} transfert(s) externes pending.",
        )
        push_action("Verifier la file des transferts externes et les validations operateur en attente.")

    if overdue_follow_up >= 10:
        push_alert(
            "critical",
            "ops_overdue_follow_up_critical",
            "Follow-up OPS en retard",
            f"{overdue_follow_up} dossier(s) avec follow-up depasse.",
        )
        push_action("Traiter les dossiers avec follow-up depasse avant de prendre de nouveaux tickets non urgents.")
    elif overdue_follow_up >= 1:
        push_alert(
            "warning",
            "ops_overdue_follow_up_warn",
            "Follow-up OPS depasses",
            f"{overdue_follow_up} dossier(s) avec follow-up en retard.",
        )

    if blocked_only >= 15:
        push_alert(
            "warning",
            "ops_blocked_high",
            "Volume OPS bloque eleve",
            f"{blocked_only} dossier(s) actuellement bloques.",
        )
        push_action("Repartir les dossiers bloques par owner et lever les blocages prioritaires.")

    if stale_urgencies >= 5:
        push_alert(
            "warning",
            "ops_stale_urgencies_high",
            "Urgences OPS stale nombreuses",
            f"{stale_urgencies} urgence(s) stale detectee(s).",
        )
        push_action("Passer par la file 'Urgences OPS' et vider en priorite les dossiers stale.")

    if not alerts:
        push_action("Aucune alerte critique detectee. Continuer la surveillance standard.")

    return alerts, actions


def _build_urgency_sla_trend(urgency_items: list[dict], *, days: int = 7) -> list[dict]:
    safe_days = max(1, min(int(days or 7), 30))
    now = datetime.now(timezone.utc)
    buckets: list[dict] = []
    index_by_day: dict[str, dict] = {}

    for offset in range(safe_days - 1, -1, -1):
        day = (now - timedelta(days=offset)).date()
        day_key = day.isoformat()
        row = {
            "date": day_key,
            "total": 0,
            "stale": 0,
            "critical": 0,
            "escrow": 0,
            "p2p_dispute": 0,
            "payment_intent": 0,
        }
        buckets.append(row)
        index_by_day[day_key] = row

    for item in urgency_items:
        last_action_at = item.get("last_action_at")
        if not last_action_at:
            continue
        try:
            action_dt = datetime.fromisoformat(str(last_action_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        day_key = action_dt.date().isoformat()
        bucket = index_by_day.get(day_key)
        if not bucket:
            continue
        kind = str(item.get("kind") or "").strip().lower()
        bucket["total"] += 1
        if bool(item.get("stale")):
            bucket["stale"] += 1
        if str(item.get("priority") or "").strip().lower() == "critical":
            bucket["critical"] += 1
        if kind in {"escrow", "p2p_dispute", "payment_intent"}:
            bucket[kind] += 1

    return buckets


def _build_ops_runbook_items(alerts: list[dict]) -> list[dict]:
    items: list[dict] = []
    seen_codes: set[str] = set()

    def push(code: str, title: str, route: str, rationale: str) -> None:
        if code in seen_codes:
            return
        seen_codes.add(code)
        items.append(
            {
                "code": code,
                "title": title,
                "route": route,
                "rationale": rationale,
            }
        )

    for alert in alerts:
        code = str(alert.get("code") or "")
        if code == "ledger_unbalanced":
            push(code, "Corriger les journaux non equilibres", "/dashboard/admin/ledger/unbalanced-journals", "Le ledger n'est pas equilibré.")
        elif code in {"api_5xx_spike", "api_5xx_present"}:
            push(code, "Inspecter les erreurs API", "/dashboard/admin/ops/errors", "Des erreurs 5xx sont detectees.")
        elif code in {"webhook_failed_retry", "webhook_retry_queue_critical", "webhook_retry_queue_warn"}:
            push(code, "Traiter les webhooks en anomalie", "/dashboard/admin/webhooks", "Des webhooks echouent ou restent en file.")
        elif code in {"external_transfers_pending_high"}:
            push(code, "Verifier les transferts en attente", "/dashboard/admin/transfers", "Le volume de transferts pending est eleve.")
        elif code in {"ops_overdue_follow_up_critical", "ops_overdue_follow_up_warn", "ops_blocked_high", "ops_stale_urgencies_high"}:
            push(code, "Vider la file Urgences OPS", "/dashboard/admin/ops-urgencies", "Des dossiers OPS sont en retard, bloques ou stale.")

    if not items:
        push("ops_monitoring_ok", "Surveillance standard", "/dashboard/admin/ops-dashboard", "Aucune alerte critique active.")
    return items


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
    workflow_summary = await fetch_operator_workflow_summary(
        db,
        current_user_id=str(getattr(user, "user_id", "") or ""),
        current_owner_label=getattr(user, "full_name", None) or getattr(user, "email", None),
    )
    urgency_items = await fetch_operator_urgency_items(db)
    urgency_by_kind: dict[str, int] = {}
    stale_urgencies = 0
    critical_urgencies = 0
    for item in urgency_items:
        kind = str(item.get("kind") or "unknown")
        urgency_by_kind[kind] = int(urgency_by_kind.get(kind) or 0) + 1
        if bool(item.get("stale")):
            stale_urgencies += 1
        if str(item.get("priority") or "").lower() == "critical":
            critical_urgencies += 1
    urgency_sla_trend = _build_urgency_sla_trend(urgency_items, days=min(int(window_hours // 24) + 1, 7))

    ops_status = _compute_ops_status(
        unbalanced_journals=unbalanced,
        errors_5xx=int(api_errors_5xx or 0),
        error_rate_percent=float(error_rate_percent or 0),
        latency_p95_ms=float(api_latency_p95_ms or 0),
        failed_retry=int(webhook_row["failed_retry"] or 0),
        retry_queue_size=int(retries_queue or 0),
    )
    alerts, recommended_actions = _build_ops_alerts_and_actions(
        errors_5xx=int(api_errors_5xx or 0),
        error_rate_percent=float(error_rate_percent or 0),
        latency_p95_ms=float(api_latency_p95_ms or 0),
        failed_retry=int(webhook_row["failed_retry"] or 0),
        retry_queue_size=int(retries_queue or 0),
        unbalanced_journals=int(unbalanced or 0),
        pending_idempotency_keys=int(idem_row["pending_keys"] or 0),
        pending_external_transfers=int(transfer_row["pending"] or 0),
        overdue_follow_up=int(workflow_summary.get("overdue_follow_up") or 0),
        blocked_only=int(workflow_summary.get("blocked_only") or 0),
        stale_urgencies=int(stale_urgencies or 0),
    )
    recommended_runbooks = _build_ops_runbook_items(alerts)

    return {
        "window_hours": window_hours,
        "status": ops_status,
        "alerts": alerts,
        "recommended_actions": recommended_actions,
        "recommended_runbooks": recommended_runbooks,
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
        "ops_workflow": {
            "all": int(workflow_summary.get("all") or 0),
            "mine": int(workflow_summary.get("mine") or 0),
            "team": int(workflow_summary.get("team") or 0),
            "unassigned": int(workflow_summary.get("unassigned") or 0),
            "blocked_only": int(workflow_summary.get("blocked_only") or 0),
            "needs_follow_up": int(workflow_summary.get("needs_follow_up") or 0),
            "watching": int(workflow_summary.get("watching") or 0),
            "resolved": int(workflow_summary.get("resolved") or 0),
            "overdue_follow_up": int(workflow_summary.get("overdue_follow_up") or 0),
        },
        "ops_urgencies": {
            "total": len(urgency_items),
            "stale": int(stale_urgencies or 0),
            "critical": int(critical_urgencies or 0),
            "by_kind": urgency_by_kind,
            "sla_trend": urgency_sla_trend,
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
    workflow_block = payload.get("ops_workflow") or {}
    urgencies_block = payload.get("ops_urgencies") or {}

    rows = [
        ("generated_at_utc", now_utc),
        ("window_hours", payload.get("window_hours")),
        ("status", payload.get("status")),
        ("alerts.count", len(payload.get("alerts") or [])),
        ("recommended_actions.count", len(payload.get("recommended_actions") or [])),
        ("recommended_runbooks.count", len(payload.get("recommended_runbooks") or [])),
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
        ("ops_workflow.all", workflow_block.get("all")),
        ("ops_workflow.unassigned", workflow_block.get("unassigned")),
        ("ops_workflow.blocked_only", workflow_block.get("blocked_only")),
        ("ops_workflow.overdue_follow_up", workflow_block.get("overdue_follow_up")),
        ("ops_urgencies.total", urgencies_block.get("total")),
        ("ops_urgencies.stale", urgencies_block.get("stale")),
        ("ops_urgencies.critical", urgencies_block.get("critical")),
        ("ops_urgencies.by_kind.escrow", (urgencies_block.get("by_kind") or {}).get("escrow")),
        ("ops_urgencies.by_kind.p2p_dispute", (urgencies_block.get("by_kind") or {}).get("p2p_dispute")),
        ("ops_urgencies.by_kind.payment_intent", (urgencies_block.get("by_kind") or {}).get("payment_intent")),
    ]

    for point in urgencies_block.get("sla_trend") or []:
        day = point.get("date")
        rows.extend(
            [
                (f"ops_urgencies.sla_trend.{day}.total", point.get("total")),
                (f"ops_urgencies.sla_trend.{day}.stale", point.get("stale")),
                (f"ops_urgencies.sla_trend.{day}.critical", point.get("critical")),
                (f"ops_urgencies.sla_trend.{day}.escrow", point.get("escrow")),
                (f"ops_urgencies.sla_trend.{day}.p2p_dispute", point.get("p2p_dispute")),
                (f"ops_urgencies.sla_trend.{day}.payment_intent", point.get("payment_intent")),
            ]
        )

    for item in payload.get("recommended_runbooks") or []:
        rows.extend(
            [
                (f"recommended_runbooks.{item.get('code')}.title", item.get("title")),
                (f"recommended_runbooks.{item.get('code')}.route", item.get("route")),
            ]
        )

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

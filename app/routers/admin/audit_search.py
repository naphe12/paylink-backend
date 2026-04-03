from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import admin_required

router = APIRouter(prefix="/admin/audit", tags=["Admin Audit Search"])

STEP_UP_ACTIONS = ("ADMIN_STEP_UP_CHECK", "ADMIN_STEP_UP_ISSUED")


def _normalize_json_field(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _serialize_audit_row(row) -> dict:
    payload = dict(row)
    payload["before_state"] = _normalize_json_field(payload.get("before_state"))
    payload["after_state"] = _normalize_json_field(payload.get("after_state"))
    return payload


def _build_combined_query() -> str:
    return """
    WITH classified_audit_rows AS (
        SELECT
            CASE
                WHEN COALESCE(a.entity_type, '') IN ('p2p_trade', 'p2p_dispute') THEN 'p2p'
                WHEN COALESCE(a.entity_type, '') = 'escrow_order' THEN 'escrow'
                WHEN COALESCE(a.entity_type, '') = 'payment_intent' THEN 'payment_intent'
                ELSE 'audit'
            END::text AS source,
            'audit_log'::text AS event_type,
            a.id::text AS raw_ref,
            a.id AS raw_id,
            a.created_at,
            a.action,
            NULL::text AS outcome,
            a.actor_user_id::text AS actor_user_id,
            COALESCE(u.full_name, '') AS actor_full_name,
            COALESCE(u.email, '') AS actor_email,
            COALESCE(a.actor_role, '') AS actor_role,
            COALESCE(a.entity_type, '') AS target_type,
            COALESCE(a.entity_id::text, '') AS target_id,
            COALESCE(a.after_state->>'request_id', '') AS request_id,
            TRIM(
                CONCAT_WS(
                    ' ',
                    COALESCE(a.action, ''),
                    COALESCE(a.entity_type, ''),
                    COALESCE(a.entity_id::text, ''),
                    COALESCE(a.after_state->>'status', ''),
                    COALESCE(a.after_state->>'resolution', ''),
                    COALESCE(a.after_state->>'reason', ''),
                    COALESCE(a.after_state->>'requested_action', '')
                )
            ) AS summary
        FROM paylink.audit_log a
        LEFT JOIN paylink.users u
          ON u.user_id = a.actor_user_id
        WHERE NOT (a.action = ANY(CAST(:step_up_actions AS text[])))
    ),
    audit_rows AS (
        SELECT * FROM classified_audit_rows
    ),
    step_up_rows AS (
        SELECT
            'step_up'::text AS source,
            'admin_step_up'::text AS event_type,
            a.id::text AS raw_ref,
            a.id AS raw_id,
            a.created_at,
            a.action,
            NULLIF(COALESCE(a.after_state->>'outcome', CASE WHEN a.action = 'ADMIN_STEP_UP_ISSUED' THEN 'issued' ELSE '' END), '') AS outcome,
            a.actor_user_id::text AS actor_user_id,
            COALESCE(u.full_name, '') AS actor_full_name,
            COALESCE(u.email, '') AS actor_email,
            COALESCE(a.actor_role, '') AS actor_role,
            NULLIF(COALESCE(a.after_state->>'target_type', CASE WHEN a.entity_type = 'ADMIN_STEP_UP' THEN '' ELSE a.entity_type END), '') AS target_type,
            NULLIF(COALESCE(a.after_state->>'target_id', a.entity_id::text, ''), '') AS target_id,
            COALESCE(a.after_state->>'request_id', '') AS request_id,
            TRIM(
                CONCAT_WS(
                    ' ',
                    COALESCE(a.after_state->>'requested_action', ''),
                    COALESCE(a.after_state->>'outcome', CASE WHEN a.action = 'ADMIN_STEP_UP_ISSUED' THEN 'issued' ELSE '' END),
                    COALESCE(a.after_state->>'code', ''),
                    COALESCE(a.after_state->>'target_type', ''),
                    COALESCE(a.after_state->>'target_id', '')
                )
            ) AS summary
        FROM paylink.audit_log a
        LEFT JOIN paylink.users u
          ON u.user_id = a.actor_user_id
        WHERE a.action = ANY(CAST(:step_up_actions AS text[]))
    ),
    combined AS (
        SELECT * FROM audit_rows
        UNION ALL
        SELECT * FROM step_up_rows
    )
    """


def _build_combined_filters(
    *,
    source: str | None,
    outcome: str | None,
    action: str | None,
    role: str | None,
    q: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    target_id: str | None,
    request_id: str | None,
):
    where = ["1=1"]
    params: dict[str, object] = {"step_up_actions": STEP_UP_ACTIONS}
    if source:
        where.append("source = :source")
        params["source"] = str(source).strip().lower()
    if outcome:
        where.append("COALESCE(outcome, '') = :outcome")
        params["outcome"] = str(outcome).strip().lower()
    if action:
        where.append("COALESCE(action, '') = :action")
        params["action"] = str(action).strip()
    if role:
        where.append("COALESCE(actor_role, '') = :role")
        params["role"] = str(role).strip().lower()
    if date_from:
        where.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("created_at <= :date_to")
        params["date_to"] = date_to
    if target_id:
        where.append("COALESCE(target_id, '') ILIKE :target_id")
        params["target_id"] = f"%{str(target_id).strip()}%"
    if request_id:
        where.append("COALESCE(request_id, '') ILIKE :request_id")
        params["request_id"] = f"%{str(request_id).strip()}%"
    if q:
        where.append(
            """
            (
                COALESCE(actor_user_id, '') ILIKE :search
                OR COALESCE(actor_full_name, '') ILIKE :search
                OR COALESCE(actor_email, '') ILIKE :search
                OR COALESCE(action, '') ILIKE :search
                OR COALESCE(target_type, '') ILIKE :search
                OR COALESCE(target_id, '') ILIKE :search
                OR COALESCE(request_id, '') ILIKE :search
                OR COALESCE(summary, '') ILIKE :search
                OR COALESCE(outcome, '') ILIKE :search
            )
            """
        )
        params["search"] = f"%{str(q).strip()}%"
    return where, params


@router.get("/search")
async def search_admin_audit(
    q: str | None = Query(None),
    source: str | None = Query(None),
    outcome: str | None = Query(None),
    action: str | None = Query(None),
    role: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    target_id: str | None = Query(None),
    request_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_required),
):
    where, params = _build_combined_filters(
        source=source,
        outcome=outcome,
        action=action,
        role=role,
        q=q,
        date_from=date_from,
        date_to=date_to,
        target_id=target_id,
        request_id=request_id,
    )
    params.update({"limit": int(limit), "offset": int(offset)})
    base_query = _build_combined_query()
    where_sql = " AND ".join(where)

    total_result = await db.execute(
        text(
            f"""
            {base_query}
            SELECT COUNT(*)
            FROM combined
            WHERE {where_sql}
            """
        ),
        params,
    )
    total = int(total_result.scalar() or 0)

    rows_result = await db.execute(
        text(
            f"""
            {base_query}
            SELECT
                source,
                created_at,
                event_type,
                action,
                outcome,
                actor_user_id,
                actor_full_name,
                actor_email,
                actor_role,
                target_type,
                target_id,
                request_id,
                summary,
                raw_ref
            FROM combined
            WHERE {where_sql}
            ORDER BY created_at DESC, raw_id DESC
            LIMIT :limit
            OFFSET :offset
            """
        ),
        params,
    )
    rows = rows_result.mappings().all()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
    }


@router.get("/search/{source}/{raw_ref}")
async def get_admin_audit_detail(
    source: str,
    raw_ref: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_required),
):
    normalized_source = str(source).strip().lower()
    try:
        raw_id = int(raw_ref)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Identifiant audit invalide") from exc

    if normalized_source == "audit":
        query = text(
            """
            SELECT a.*, u.full_name AS actor_full_name, u.email AS actor_email
            FROM paylink.audit_log a
            LEFT JOIN paylink.users u
              ON u.user_id = a.actor_user_id
            WHERE a.id = :raw_id
              AND NOT (a.action = ANY(CAST(:step_up_actions AS text[])))
            """
        )
    elif normalized_source == "step_up":
        query = text(
            """
            SELECT a.*, u.full_name AS actor_full_name, u.email AS actor_email
            FROM paylink.audit_log a
            LEFT JOIN paylink.users u
              ON u.user_id = a.actor_user_id
            WHERE a.id = :raw_id
              AND a.action = ANY(CAST(:step_up_actions AS text[]))
            """
        )
    else:
        raise HTTPException(status_code=400, detail="Source audit invalide")

    result = await db.execute(query, {"raw_id": raw_id, "step_up_actions": STEP_UP_ACTIONS})
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Entree audit introuvable")

    payload = _serialize_audit_row(row)
    return {
        "source": normalized_source,
        "raw_ref": str(raw_ref),
        "raw": payload,
    }

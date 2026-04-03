import csv
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from app.core.database import get_db
from app.models.users import Users
from app.core.security import admin_required
from app.models.security_logs import SecurityLogs
from sqlalchemy import UUID
from fastapi import HTTPException
router = APIRouter(prefix="/admin/risk", tags=["Admin Risk Monitor"])


STEP_UP_EXPORT_HEADERS = [
    "created_at",
    "request_id",
    "action",
    "outcome",
    "requested_action",
    "target_type",
    "target_id",
    "code",
    "method",
    "status_code",
    "session_bound",
    "actor_user_id",
    "actor_full_name",
    "actor_email",
    "actor_role",
    "ip",
    "user_agent",
]

STEP_UP_EVENT_WHERE = """
(
    a.action = 'ADMIN_STEP_UP_CHECK'
    OR a.action = 'ADMIN_STEP_UP_ISSUED'
)
"""

@router.get("/users")
async def get_risky_users(
    min_score: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_required)
):
    q = (
        select(Users.user_id, Users.full_name, Users.email, Users.risk_score, Users.kyc_tier)
        .where(Users.risk_score >= min_score)
        .order_by(Users.risk_score.desc())
    )
    result = (await db.execute(q)).mappings().all()
    return list(result)

@router.post("/reset/{user_id}")
async def reset_risk(user_id: str, db: AsyncSession = Depends(get_db), _=Depends(admin_required)):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        return {"error": "User not found"}

    user.risk_score = 0
    await db.commit()
    return {"message": "✅ Risque remis à zéro"}

@router.get("/admin/security/logs")
async def get_security_logs(db: AsyncSession = Depends(get_db)):
    q = select(SecurityLogs).order_by(SecurityLogs.created_at.desc()).limit(50)
    logs = (await db.execute(q)).scalars().all()
    return logs


@router.get("/step-up-events")
async def get_admin_step_up_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    outcome: str | None = Query(None),
    requested_action: str | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_required),
):
    params = {"limit": int(limit), "offset": int(offset)}
    where_clauses = [STEP_UP_EVENT_WHERE]
    if outcome:
        where_clauses.append("COALESCE(a.after_state->>'outcome', '') = :outcome")
        params["outcome"] = str(outcome).strip().lower()
    if requested_action:
        where_clauses.append("COALESCE(a.after_state->>'requested_action', '*') = :requested_action")
        params["requested_action"] = str(requested_action).strip()
    if q:
        where_clauses.append(
            """
            (
                COALESCE(u.full_name, '') ILIKE :search
                OR COALESCE(u.email, '') ILIKE :search
                OR COALESCE(a.after_state->>'code', '') ILIKE :search
                OR COALESCE(a.after_state->>'requested_action', '') ILIKE :search
            )
            """
        )
        params["search"] = f"%{str(q).strip()}%"

    where_sql = " AND ".join(where_clauses)
    total_query = text(
        f"""
        SELECT COUNT(*)
        FROM paylink.audit_log a
        LEFT JOIN paylink.users u
          ON u.user_id = a.actor_user_id
        WHERE {where_sql}
        """
    )
    total = int((await db.execute(total_query, params)).scalar() or 0)

    items_query = text(
        f"""
        SELECT
            a.id,
            a.created_at,
            a.action,
            a.actor_user_id,
            a.actor_role,
            u.full_name AS actor_full_name,
            u.email AS actor_email,
            COALESCE(a.after_state->>'requested_action', '*') AS requested_action,
            COALESCE(a.after_state->>'outcome', CASE WHEN a.action = 'ADMIN_STEP_UP_ISSUED' THEN 'issued' ELSE '' END) AS outcome,
            COALESCE(a.after_state->>'request_id', '') AS request_id,
            COALESCE(a.after_state->>'target_type', CASE WHEN a.entity_type = 'ADMIN_STEP_UP' THEN '' ELSE a.entity_type END) AS target_type,
            COALESCE(a.after_state->>'target_id', COALESCE(a.entity_id::text, '')) AS target_id,
            COALESCE(a.after_state->>'code', '') AS code,
            COALESCE(a.after_state->>'method', '') AS method,
            COALESCE((a.after_state->>'status_code')::int, NULL) AS status_code,
            COALESCE((a.after_state->>'session_bound')::boolean, FALSE) AS session_bound,
            a.ip,
            a.user_agent
        FROM paylink.audit_log a
        LEFT JOIN paylink.users u
          ON u.user_id = a.actor_user_id
        WHERE {where_sql}
        ORDER BY a.created_at DESC
        LIMIT :limit
        OFFSET :offset
        """
    )
    rows = (await db.execute(items_query, params)).mappings().all()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
    }


@router.get("/step-up-summary")
async def get_admin_step_up_summary(
    window_hours: int = Query(24, ge=1, le=24 * 30),
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_required),
):
    params = {"window_hours": int(window_hours)}
    summary_query = text(
        f"""
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE COALESCE(a.after_state->>'outcome', CASE WHEN a.action = 'ADMIN_STEP_UP_ISSUED' THEN 'issued' ELSE '' END) = 'issued')::int AS issued,
            COUNT(*) FILTER (WHERE COALESCE(a.after_state->>'outcome', '') = 'verified')::int AS verified,
            COUNT(*) FILTER (WHERE COALESCE(a.after_state->>'outcome', '') = 'denied')::int AS denied,
            COUNT(*) FILTER (WHERE COALESCE(a.after_state->>'outcome', '') = 'required')::int AS required
        FROM paylink.audit_log a
        WHERE {STEP_UP_EVENT_WHERE}
          AND a.created_at >= NOW() - make_interval(hours => :window_hours)
        """
    )
    summary_row = (await db.execute(summary_query, params)).mappings().first() or {}

    denied_codes_query = text(
        f"""
        SELECT
            COALESCE(a.after_state->>'code', 'unknown') AS code,
            COUNT(*)::int AS count
        FROM paylink.audit_log a
        WHERE {STEP_UP_EVENT_WHERE}
          AND a.created_at >= NOW() - make_interval(hours => :window_hours)
          AND COALESCE(a.after_state->>'outcome', '') = 'denied'
        GROUP BY COALESCE(a.after_state->>'code', 'unknown')
        ORDER BY count DESC, code ASC
        LIMIT 5
        """
    )
    denied_codes = [dict(row) for row in (await db.execute(denied_codes_query, params)).mappings().all()]

    action_query = text(
        f"""
        SELECT
            COALESCE(a.after_state->>'requested_action', '*') AS requested_action,
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE COALESCE(a.after_state->>'outcome', '') = 'denied')::int AS denied,
            COUNT(*) FILTER (WHERE COALESCE(a.after_state->>'outcome', '') = 'verified')::int AS verified,
            COUNT(*) FILTER (WHERE COALESCE(a.after_state->>'outcome', '') = 'required')::int AS required
        FROM paylink.audit_log a
        WHERE {STEP_UP_EVENT_WHERE}
          AND a.created_at >= NOW() - make_interval(hours => :window_hours)
        GROUP BY COALESCE(a.after_state->>'requested_action', '*')
        ORDER BY total DESC, requested_action ASC
        LIMIT 10
        """
    )
    by_action = [dict(row) for row in (await db.execute(action_query, params)).mappings().all()]

    return {
        "window_hours": int(window_hours),
        "totals": {
            "total": int(summary_row.get("total") or 0),
            "issued": int(summary_row.get("issued") or 0),
            "verified": int(summary_row.get("verified") or 0),
            "denied": int(summary_row.get("denied") or 0),
            "required": int(summary_row.get("required") or 0),
        },
        "denied_codes": denied_codes,
        "by_action": by_action,
    }


@router.get("/step-up-events/export.csv")
async def export_admin_step_up_events_csv(
    limit: int = Query(5000, ge=1, le=10000),
    outcome: str | None = Query(None),
    requested_action: str | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_required),
):
    rows = await get_admin_step_up_events(
        limit=limit,
        offset=0,
        outcome=outcome,
        requested_action=requested_action,
        q=q,
        db=db,
        _=_,
    )
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(STEP_UP_EXPORT_HEADERS)
    for row in rows["items"]:
        writer.writerow([row.get(header, "") for header in STEP_UP_EXPORT_HEADERS])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=admin_step_up_events.csv"},
    )

@router.post("/admin/unfreeze/{user_id}", response_model=None)
async def unfreeze_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        update(Users)
        .where(Users.user_id == user_id)
        .values(account_status="active")
        .returning(Users.user_id)
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    await db.commit()

    return {"status": "unfroze", "user_id": user_id}



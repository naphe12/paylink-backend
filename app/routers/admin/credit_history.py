from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.credit_line_events import CreditLineEvents
from app.models.credit_line_history import CreditLineHistory
from app.models.credit_lines import CreditLines
from app.models.users import Users

router = APIRouter(prefix="/admin/credit-history", tags=["Admin Credit History"])


@router.get("/users")
async def list_credit_history_users(
    mode: str = Query("all"),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    normalized_mode = str(mode or "all").strip().lower()

    history_users_stmt = (
        select(CreditLineHistory.user_id.label("user_id"))
        .group_by(CreditLineHistory.user_id)
    )
    event_users_stmt = (
        select(CreditLineEvents.user_id.label("user_id"))
        .group_by(CreditLineEvents.user_id)
    )

    if normalized_mode == "history":
        user_ids_subquery = history_users_stmt.subquery()
    elif normalized_mode == "events":
        user_ids_subquery = event_users_stmt.subquery()
    else:
        user_ids_subquery = history_users_stmt.union(event_users_stmt).subquery()

    stmt = (
        select(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
        )
        .join(user_ids_subquery, user_ids_subquery.c.user_id == Users.user_id)
        .where(Users.role == "client")
        .order_by(Users.full_name.asc(), Users.created_at.desc())
        .limit(limit)
    )

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            (Users.full_name.ilike(pattern))
            | (Users.email.ilike(pattern))
            | (Users.phone_e164.ilike(pattern))
        )

    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": str(user_id),
            "full_name": full_name,
            "email": email,
            "phone_e164": phone_e164,
        }
        for user_id, full_name, email, phone_e164 in rows
    ]


@router.get("/")
async def list_credit_history(
    user_id: UUID | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    stmt = select(CreditLineHistory, Users.full_name, Users.email).outerjoin(
        Users, Users.user_id == CreditLineHistory.user_id
    )
    count_stmt = select(func.count()).select_from(CreditLineHistory)
    if user_id:
        stmt = stmt.where(CreditLineHistory.user_id == user_id)
        count_stmt = count_stmt.where(CreditLineHistory.user_id == user_id)
    stmt = stmt.order_by(CreditLineHistory.created_at.desc()).limit(limit).offset(offset)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "entry_id": str(entry.entry_id),
                "user_id": str(entry.user_id),
                "full_name": full_name,
                "email": email,
                "transaction_id": str(entry.transaction_id) if entry.transaction_id else None,
                "amount": float(entry.amount or 0),
                "credit_available_before": float(entry.credit_available_before or 0),
                "credit_available_after": float(entry.credit_available_after or 0),
                "description": entry.description,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry, full_name, email in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/events")
async def list_credit_events(
    user_id: UUID | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    stmt = (
        select(CreditLineEvents, Users.full_name, Users.email, CreditLines.currency_code)
        .outerjoin(Users, Users.user_id == CreditLineEvents.user_id)
        .outerjoin(CreditLines, CreditLines.credit_line_id == CreditLineEvents.credit_line_id)
    )
    count_stmt = select(func.count()).select_from(CreditLineEvents)
    if user_id:
        stmt = stmt.where(CreditLineEvents.user_id == user_id)
        count_stmt = count_stmt.where(CreditLineEvents.user_id == user_id)
    stmt = stmt.order_by(CreditLineEvents.created_at.desc()).limit(limit).offset(offset)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "event_id": str(event.event_id),
                "credit_line_id": str(event.credit_line_id),
                "user_id": str(event.user_id),
                "full_name": full_name,
                "email": email,
                "amount_delta": float(event.amount_delta or 0),
                "currency_code": event.currency_code or credit_currency,
                "old_limit": float(event.old_limit) if event.old_limit is not None else None,
                "new_limit": float(event.new_limit) if event.new_limit is not None else None,
                "operation_code": event.operation_code,
                "status": event.status,
                "source": event.source,
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event, full_name, email, credit_currency in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

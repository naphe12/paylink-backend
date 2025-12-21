from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.credit_lines import CreditLines
from app.models.credit_line_events import CreditLineEvents
from app.models.users import Users

router = APIRouter(prefix="/admin/credit-lines", tags=["Admin Credit Lines"])


@router.get("")
async def list_credit_lines(
    q: Optional[str] = Query(None, description="Filtre nom/email"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(
            CreditLines.credit_line_id,
            CreditLines.user_id,
            CreditLines.currency_code,
            CreditLines.initial_amount,
            CreditLines.used_amount,
            CreditLines.outstanding_amount,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == CreditLines.user_id)
        .order_by(CreditLines.created_at.desc())
        .limit(limit)
    )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where((Users.full_name.ilike(pattern)) | (Users.email.ilike(pattern)))

    rows = (await db.execute(stmt)).all()
    return [
        {
            "credit_line_id": str(cl_id),
            "user_id": str(user_id),
            "full_name": full_name,
            "email": email,
            "currency_code": currency,
            "initial_amount": float(initial or 0),
            "used_amount": float(used or 0),
            "outstanding_amount": float(outstanding or 0),
        }
        for cl_id, user_id, currency, initial, used, outstanding, full_name, email in rows
    ]


@router.get("/{credit_line_id}")
async def get_credit_line_detail(
    credit_line_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    credit_line = await db.scalar(
        select(CreditLines).where(CreditLines.credit_line_id == credit_line_id)
    )
    if not credit_line:
        raise HTTPException(404, "Ligne de crédit introuvable")

    user = await db.scalar(select(Users).where(Users.user_id == credit_line.user_id))
    events = (
        await db.execute(
            select(CreditLineEvents)
            .where(CreditLineEvents.credit_line_id == credit_line_id)
            .order_by(CreditLineEvents.created_at.desc())
        )
    ).scalars().all()

    return {
        "credit_line": {
            "credit_line_id": str(credit_line.credit_line_id),
            "user_id": str(credit_line.user_id),
            "full_name": getattr(user, "full_name", None),
            "email": getattr(user, "email", None),
            "currency_code": credit_line.currency_code,
            "initial_amount": float(credit_line.initial_amount or 0),
            "used_amount": float(credit_line.used_amount or 0),
            "outstanding_amount": float(credit_line.outstanding_amount or 0),
            "status": credit_line.status,
            "source": credit_line.source,
            "created_at": credit_line.created_at,
            "updated_at": credit_line.updated_at,
        },
        "events": [
            {
                "event_id": str(ev.event_id),
                "amount_delta": float(ev.amount_delta or 0),
                "currency_code": ev.currency_code,
                "old_limit": float(ev.old_limit) if ev.old_limit is not None else None,
                "new_limit": float(ev.new_limit) if ev.new_limit is not None else None,
                "operation_code": ev.operation_code,
                "status": ev.status,
                "source": ev.source,
                "occurred_at": ev.occurred_at,
                "created_at": ev.created_at,
            }
            for ev in events
        ],
    }

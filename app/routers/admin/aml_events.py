from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.amlevents import AmlEvents
from app.models.transactions import Transactions
from app.models.users import Users

router = APIRouter(prefix="/admin/aml", tags=["Admin AML"])


@router.get("/events")
async def list_aml_events(
    limit: int = Query(50, ge=1, le=200),
    user_id: UUID | None = Query(None, description="Filtre un utilisateur pr��cis"),
    risk_level: str | None = Query(None, description="Filtre : low/medium/high/critical"),
    search: str | None = Query(None, description="Nom, email ou code r��gle"),
    from_date: datetime | None = Query(None, description="A partir de cette date"),
    to_date: datetime | None = Query(None, description="Jusqu'�� cette date"),
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
) -> list[dict[str, Any]]:
    stmt = (
        select(
            AmlEvents.aml_id,
            AmlEvents.created_at,
            AmlEvents.risk_level,
            AmlEvents.rule_code,
            AmlEvents.details,
            Users.user_id,
            Users.full_name,
            Users.email,
            Transactions.tx_id,
            Transactions.amount,
            Transactions.currency_code,
            Transactions.channel,
        )
        .join(Users, Users.user_id == AmlEvents.user_id, isouter=True)
        .join(Transactions, Transactions.tx_id == AmlEvents.tx_id, isouter=True)
        .order_by(AmlEvents.created_at.desc())
        .limit(limit)
    )

    if user_id:
        stmt = stmt.where(AmlEvents.user_id == user_id)
    if risk_level:
        stmt = stmt.where(AmlEvents.risk_level == risk_level)
    if from_date:
        stmt = stmt.where(AmlEvents.created_at >= from_date)
    if to_date:
        stmt = stmt.where(AmlEvents.created_at <= to_date)
    if search:
        like_pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Users.full_name.ilike(like_pattern),
                Users.email.ilike(like_pattern),
                AmlEvents.rule_code.ilike(like_pattern),
            )
        )

    rows = (await db.execute(stmt)).all()
    events: list[dict[str, Any]] = []
    for row in rows:
        details = row.details or {}
        events.append(
            {
                "event_id": str(row.aml_id),
                "created_at": row.created_at.isoformat(),
                "risk_level": row.risk_level,
                "rule_code": row.rule_code,
                "reason": row.rule_code,
                "user_id": str(row.user_id) if row.user_id else None,
                "user_name": row.full_name,
                "user_email": row.email,
                "score_delta": details.get("score_delta"),
                "new_score": details.get("new_score"),
                "old_score": details.get("old_score"),
                "amount": (
                    float(details.get("tx_amount"))
                    if details.get("tx_amount") is not None
                    else float(row.amount) if row.amount is not None else None
                ),
                "currency_code": row.currency_code,
                "channel": row.channel,
                "transaction_id": str(row.tx_id) if row.tx_id else None,
                "details": details,
            }
        )

    return events

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.credit_line_history import CreditLineHistory
from app.models.users import Users
from app.schemas.credit_line_history import CreditLineHistoryRead

router = APIRouter(prefix="/admin/credit-history", tags=["Admin Credit History"])


@router.get("/", response_model=list[CreditLineHistoryRead])
async def list_credit_history(
    user_id: UUID | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    stmt = (
        select(CreditLineHistory)
        .order_by(CreditLineHistory.created_at.desc())
        .limit(limit)
    )
    if user_id:
        stmt = stmt.where(CreditLineHistory.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        CreditLineHistoryRead.model_validate(row, from_attributes=True)
        for row in rows
    ]

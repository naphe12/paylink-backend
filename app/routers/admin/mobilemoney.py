from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.agent_transactions import AgentTransactions

router = APIRouter(prefix="/admin/mobilemoney", tags=["Admin Mobile Money"])


@router.get("/journal")
async def mobile_money_journal(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
    status: str | None = Query(None),
    direction: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    stmt = (
        select(
            Transactions,
            Users.full_name.label("customer_name"),
            Users.phone_e164.label("customer_phone"),
            AgentTransactions.commission,
            AgentTransactions.direction.label("agent_direction"),
        )
        .join(Users, Users.user_id == Transactions.initiated_by, isouter=True)
        .join(
            AgentTransactions,
            AgentTransactions.related_tx == Transactions.tx_id,
            isouter=True,
        )
        .where(Transactions.channel == "mobile_money")
        .order_by(Transactions.created_at.desc())
        .limit(limit)
    )

    if status:
        stmt = stmt.where(Transactions.status == status)
    if date_from:
        stmt = stmt.where(Transactions.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Transactions.created_at <= date_to)
    if direction:
        stmt = stmt.where(AgentTransactions.direction == direction)

    rows = await db.execute(stmt)

    return [
        {
            "tx_id": str(tx.tx_id),
            "amount": float(tx.amount),
            "currency": tx.currency_code,
            "status": tx.status,
            "channel": tx.channel,
            "description": tx.description,
            "created_at": tx.created_at.isoformat(),
            "customer": {
                "name": customer_name,
                "phone": customer_phone,
            },
            "direction": agent_direction or "mobile_money",
            "commission": float(commission or 0),
        }
        for tx, customer_name, customer_phone, commission, agent_direction in rows.all()
    ]

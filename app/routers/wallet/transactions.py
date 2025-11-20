from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.transactions import Transactions
from app.models.users import Users

router = APIRouter()

@router.get("/transactions")
async def get_user_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    result = await db.execute(
        select(Transactions)
        .where(Transactions.initiated_by == current_user.user_id)
        .order_by(Transactions.created_at.desc())
    )
    return result.scalars().all()

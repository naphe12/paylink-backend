from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_agent
from app.models.users import Users
from app.schemas.bonus import (
    AgentBonusTransferCreate,
    AgentBonusUserSummaryRead,
    BonusTransferRead,
)
from app.services.bonus_transfer_service import (
    get_agent_bonus_user_summary,
    send_bonus_by_user_ids,
)

router = APIRouter(prefix="/agent/bonus", tags=["Agent Bonus"])


@router.get("/users/{user_id}", response_model=AgentBonusUserSummaryRead)
async def get_agent_bonus_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    return await get_agent_bonus_user_summary(db, user_id=user_id)


@router.post("/send", response_model=BonusTransferRead)
async def send_agent_bonus_transfer(
    payload: AgentBonusTransferCreate,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    return await send_bonus_by_user_ids(
        db,
        sender_user_id=payload.sender_user_id,
        recipient_user_id=payload.recipient_user_id,
        amount_bif=payload.amount_bif,
        actor_user=current_agent,
    )

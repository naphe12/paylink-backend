from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.escrow_chat.schemas import EscrowChatRequest, EscrowChatResponse
from app.escrow_chat.service import cancel_escrow_request, process_escrow_message
from app.models.users import Users
from app.routers.agent._target_user import resolve_target_user_id


router = APIRouter(prefix="/agent/escrow-chat", tags=["Escrow Agent"])


@router.post("", response_model=EscrowChatResponse)
async def escrow_chat_agent(
    payload: EscrowChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await process_escrow_message(
        db,
        user_id=resolve_target_user_id(current_user, payload.target_user_id),
        message=payload.message,
    )


@router.post("/cancel", response_model=EscrowChatResponse)
async def cancel_escrow_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_escrow_request()

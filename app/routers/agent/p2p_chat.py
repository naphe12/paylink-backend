from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.p2p_chat.schemas import P2PChatRequest, P2PChatResponse
from app.p2p_chat.service import cancel_p2p_request, process_p2p_message


router = APIRouter(prefix="/agent/p2p-chat", tags=["P2P Agent"])


@router.post("", response_model=P2PChatResponse)
async def p2p_chat_agent(
    payload: P2PChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await process_p2p_message(db, user_id=current_user.user_id, message=payload.message)


@router.post("/cancel", response_model=P2PChatResponse)
async def cancel_p2p_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_p2p_request()

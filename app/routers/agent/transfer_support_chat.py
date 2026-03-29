from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.transfer_support_chat.schemas import TransferSupportChatRequest, TransferSupportChatResponse
from app.transfer_support_chat.service import (
    cancel_transfer_support_request,
    process_transfer_support_message,
)
from app.routers.agent._target_user import resolve_target_user_context


router = APIRouter(prefix="/agent/transfer-support-chat", tags=["Transfer Support Agent"])


@router.post("", response_model=TransferSupportChatResponse)
async def transfer_support_chat_agent(
    payload: TransferSupportChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    target_context = await resolve_target_user_context(
        db,
        current_user,
        payload.target_user_id,
        payload.message,
    )
    return await process_transfer_support_message(
        db,
        user_id=target_context.user_id,
        message=target_context.message,
    )


@router.post("/cancel", response_model=TransferSupportChatResponse)
async def cancel_transfer_support_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_transfer_support_request()

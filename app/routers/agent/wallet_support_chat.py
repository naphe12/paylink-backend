from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.wallet_support_chat.schemas import WalletSupportChatRequest, WalletSupportChatResponse
from app.wallet_support_chat.service import (
    cancel_wallet_support_request,
    process_wallet_support_message,
)
from app.routers.agent._target_user import resolve_target_user_context


router = APIRouter(prefix="/agent/wallet-support-chat", tags=["Wallet Support Agent"])


@router.post("", response_model=WalletSupportChatResponse)
async def wallet_support_chat_agent(
    payload: WalletSupportChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    target_context = await resolve_target_user_context(
        db,
        current_user,
        payload.target_user_id,
        payload.message,
    )
    return await process_wallet_support_message(
        db,
        user_id=target_context.user_id,
        message=target_context.message,
    )


@router.post("/cancel", response_model=WalletSupportChatResponse)
async def cancel_wallet_support_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_wallet_support_request()

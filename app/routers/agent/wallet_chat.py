from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.wallet_chat.schemas import WalletChatRequest, WalletChatResponse
from app.wallet_chat.service import cancel_wallet_request, process_wallet_message
from app.routers.agent._target_user import resolve_target_user_context


router = APIRouter(prefix="/agent/wallet-chat", tags=["Wallet Agent"])


@router.post("", response_model=WalletChatResponse)
async def wallet_chat_agent(
    payload: WalletChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    target_context = await resolve_target_user_context(
        db,
        current_user,
        payload.target_user_id,
        payload.message,
    )
    return await process_wallet_message(
        db,
        user_id=target_context.user_id,
        message=target_context.message,
    )


@router.post("/cancel", response_model=WalletChatResponse)
async def cancel_wallet_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_wallet_request()

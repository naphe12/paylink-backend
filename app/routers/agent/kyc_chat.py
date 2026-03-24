from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.kyc_chat.schemas import KycChatRequest, KycChatResponse
from app.kyc_chat.service import cancel_kyc_request, process_kyc_message
from app.models.users import Users
from app.routers.agent._target_user import resolve_target_user_id


router = APIRouter(prefix="/agent/kyc-chat", tags=["KYC Agent"])


@router.post("", response_model=KycChatResponse)
async def kyc_chat_agent(
    payload: KycChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await process_kyc_message(
        db,
        user_id=resolve_target_user_id(current_user, payload.target_user_id),
        message=payload.message,
    )


@router.post("/cancel", response_model=KycChatResponse)
async def cancel_kyc_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_kyc_request()

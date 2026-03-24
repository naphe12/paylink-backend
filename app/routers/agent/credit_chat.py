from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.credit_chat.schemas import CreditChatRequest, CreditChatResponse
from app.credit_chat.service import cancel_credit_request, process_credit_message
from app.dependencies.auth import get_current_user
from app.models.users import Users


router = APIRouter(prefix="/agent/credit-chat", tags=["Credit Agent"])


@router.post("", response_model=CreditChatResponse)
async def credit_chat_agent(
    payload: CreditChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await process_credit_message(db, user_id=current_user.user_id, message=payload.message)


@router.post("/cancel", response_model=CreditChatResponse)
async def cancel_credit_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_credit_request()

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_onboarding_chat.schemas import AgentOnboardingChatRequest, AgentOnboardingChatResponse
from app.agent_onboarding_chat.service import (
    cancel_agent_onboarding_request,
    process_agent_onboarding_message,
)
from app.core.database import get_db
from app.dependencies.auth import get_current_agent
from app.models.users import Users


router = APIRouter(prefix="/agent/onboarding-chat", tags=["Agent Onboarding"])


@router.post("", response_model=AgentOnboardingChatResponse)
async def agent_onboarding_chat(
    payload: AgentOnboardingChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_agent),
):
    return await process_agent_onboarding_message(
        db,
        current_user=current_user,
        message=payload.message,
    )


@router.post("/cancel", response_model=AgentOnboardingChatResponse)
async def cancel_agent_onboarding_chat(
    current_user: Users = Depends(get_current_agent),
):
    return cancel_agent_onboarding_request()

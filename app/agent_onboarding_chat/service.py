from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.legacy_adapters import handle_agent_onboarding_with_ai
from app.agent_onboarding_chat.catalog import GUIDES, SCENARIOS, build_onboarding_suggestions
from app.agent_onboarding_chat.parser import parse_agent_onboarding_message
from app.agent_onboarding_chat.schemas import AgentOnboardingChatResponse
from app.models.users import Users


async def process_agent_onboarding_message(
    db: AsyncSession | None = None,
    *,
    current_user: Users | None = None,
    message: str,
) -> AgentOnboardingChatResponse:
    if db is not None and current_user is not None:
        ai_response, handled = await handle_agent_onboarding_with_ai(
            db,
            current_user=current_user,
            message=message,
        )
        if handled:
            return ai_response
    draft = parse_agent_onboarding_message(message)
    scenario = SCENARIOS.get(draft.scenario)
    if scenario:
        return AgentOnboardingChatResponse(
            status="INFO",
            message=scenario["message"],
            data=draft,
            assumptions=scenario.get("assumptions", []),
            summary=scenario.get("summary"),
        )

    guide = GUIDES.get(draft.intent)
    if not guide:
        return AgentOnboardingChatResponse(
            status="NEED_INFO",
            message="Je peux guider sur cash-in, cash-out, scan QR, transfert externe, verifications client et erreurs frequentes.",
            data=draft,
            suggestions=build_onboarding_suggestions(),
        )

    return AgentOnboardingChatResponse(
        status="INFO",
        message=guide["message"],
        data=draft,
        assumptions=guide.get("assumptions", []),
        summary=guide.get("summary"),
    )


def cancel_agent_onboarding_request() -> AgentOnboardingChatResponse:
    return AgentOnboardingChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)

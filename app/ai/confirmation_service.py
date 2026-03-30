from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation_state import AiConversationState
from app.models.ai_pending_actions import AiPendingActions
from app.models.users import Users


async def load_conversation_state(db: AsyncSession, session_id: UUID | None, user_id) -> AiConversationState | None:
    if session_id is None:
        return None
    return await db.scalar(
        select(AiConversationState).where(
            AiConversationState.session_id == session_id,
            AiConversationState.user_id == user_id,
        )
    )


async def save_conversation_state(
    db: AsyncSession,
    *,
    session_id: UUID | None,
    current_user: Users,
    current_intent: str,
    collected_slots: dict,
) -> None:
    if session_id is None:
        return
    state = await load_conversation_state(db, session_id, current_user.user_id)
    if state is None:
        state = AiConversationState(
            session_id=session_id,
            user_id=current_user.user_id,
            current_intent=current_intent,
            collected_slots=collected_slots,
            state="active",
        )
        db.add(state)
    else:
        state.current_intent = current_intent
        state.collected_slots = collected_slots
        state.state = "active"
        state.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def clear_conversation_state(db: AsyncSession, session_id: UUID | None, user_id) -> None:
    state = await load_conversation_state(db, session_id, user_id)
    if state is None:
        return
    state.state = "completed"
    state.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def create_pending_action(
    db: AsyncSession,
    *,
    current_user: Users,
    session_id: UUID | None,
    intent_code: str,
    action_code: str,
    payload: dict,
) -> AiPendingActions:
    pending = AiPendingActions(
        user_id=current_user.user_id,
        session_id=session_id,
        intent_code=intent_code,
        action_code=action_code,
        payload=payload,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(pending)
    await db.flush()
    return pending


async def load_pending_action(db: AsyncSession, *, pending_action_id: UUID, current_user: Users) -> AiPendingActions | None:
    return await db.scalar(
        select(AiPendingActions).where(
            AiPendingActions.id == pending_action_id,
            AiPendingActions.user_id == current_user.user_id,
        )
    )


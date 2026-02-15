from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_service import audit_log


async def audit(
    db: AsyncSession,
    actor_user_id,
    actor_role: str,
    action: str,
    metadata: dict,
    entity_type=None,
    entity_id=None,
    ip=None,
    user_agent=None,
):
    await audit_log(
        db,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type or "SYSTEM",
        entity_id=entity_id,
        before_state=None,
        after_state=metadata,
        ip=ip,
        user_agent=user_agent,
    )

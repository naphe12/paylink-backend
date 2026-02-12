from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def audit_log(
    db: AsyncSession,
    *,
    actor_user_id: str | None,
    actor_role: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
):
    await db.execute(text("""
        INSERT INTO paylink.audit_log
          (actor_user_id, actor_role, action, entity_type, entity_id, before_state, after_state, ip, user_agent)
        VALUES
          (CAST(:actor_user_id AS uuid), :actor_role, :action, :entity_type, CAST(:entity_id AS uuid),
           CAST(:before_state AS jsonb), CAST(:after_state AS jsonb), :ip, :user_agent)
    """), {
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_state": before_state,
        "after_state": after_state,
        "ip": ip,
        "user_agent": user_agent,
    })


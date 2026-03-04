from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users

router = APIRouter(prefix="/backoffice/audit", tags=["Backoffice - Audit"])


def _require_admin(user: Users) -> None:
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")

@router.get("")
async def list_audit(
    limit: int = 200,
    action: str | None = None,
    entity_type: str | None = None,
    actor_role: str | None = None,
    query: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_admin(user)
    where = []
    params = {"limit": limit}
    if action:
        where.append("action = :action")
        params["action"] = action
    if entity_type:
        where.append("entity_type = :entity_type")
        params["entity_type"] = entity_type
    if actor_role:
        where.append("actor_role = :actor_role")
        params["actor_role"] = actor_role
    if query:
        where.append(
            """
            (
              CAST(id AS text) ILIKE :pattern
              OR COALESCE(action, '') ILIKE :pattern
              OR COALESCE(entity_type, '') ILIKE :pattern
              OR COALESCE(CAST(entity_id AS text), '') ILIKE :pattern
              OR COALESCE(CAST(actor_user_id AS text), '') ILIKE :pattern
            )
            """
        )
        params["pattern"] = f"%{query.strip()}%"
    sql = """
      SELECT id, created_at, actor_user_id, actor_role, action, entity_type, entity_id
      FROM paylink.audit_log
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT :limit"
    res = await db.execute(text(sql), params)
    return [dict(r._mapping) for r in res.fetchall()]

@router.get("/{audit_id}")
async def audit_detail(
    audit_id: int,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_admin(user)
    res = await db.execute(text("SELECT * FROM paylink.audit_log WHERE id=:id"), {"id": audit_id})
    row = res.first()
    return dict(row._mapping) if row else None

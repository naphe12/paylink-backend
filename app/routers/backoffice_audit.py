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
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_admin(user)
    res = await db.execute(text("""
      SELECT id, created_at, actor_user_id, actor_role, action, entity_type, entity_id
      FROM paylink.audit_log
      ORDER BY created_at DESC
      LIMIT :limit
    """), {"limit": limit})
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

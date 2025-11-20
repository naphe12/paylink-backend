from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.database import get_db
from app.models.users import Users
from app.core.security import admin_required
from app.models.security_logs import SecurityLogs
from sqlalchemy import UUID
from fastapi import HTTPException
router = APIRouter(prefix="/admin/risk", tags=["Admin Risk Monitor"])

@router.get("/users")
async def get_risky_users(
    min_score: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_required)
):
    q = (
        select(Users.user_id, Users.full_name, Users.email, Users.risk_score, Users.kyc_tier)
        .where(Users.risk_score >= min_score)
        .order_by(Users.risk_score.desc())
    )
    result = (await db.execute(q)).mappings().all()
    return list(result)

@router.post("/reset/{user_id}")
async def reset_risk(user_id: str, db: AsyncSession = Depends(get_db), _=Depends(admin_required)):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        return {"error": "User not found"}

    user.risk_score = 0
    await db.commit()
    return {"message": "✅ Risque remis à zéro"}

@router.get("/admin/security/logs")
async def get_security_logs(db: AsyncSession = Depends(get_db)):
    q = select(SecurityLogs).order_by(SecurityLogs.created_at.desc()).limit(50)
    logs = (await db.execute(q)).scalars().all()
    return logs

@router.post("/admin/unfreeze/{user_id}", response_model=None)
async def unfreeze_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        update(Users)
        .where(Users.user_id == user_id)
        .values(account_status="active")
        .returning(Users.user_id)
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    await db.commit()

    return {"status": "unfroze", "user_id": user_id}



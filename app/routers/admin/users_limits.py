# app/routers/admin/users_limits.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.database import get_db
from app.core.security import admin_required
from app.models.users import Users
from pydantic import BaseModel, Field
from decimal import Decimal


router = APIRouter(prefix="/admin/users", tags=["admin:users"])

class LimitsPayload(BaseModel):
    daily_limit: Decimal = Field(gt=0)
    monthly_limit: Decimal = Field(gt=0)



@router.patch("/{user_id}/limits", dependencies=[Depends(admin_required)])
async def update_user_limits(user_id: str, body: LimitsPayload, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(Users).where(Users.user_id==user_id))
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    await db.execute(
        update(Users)
        .where(Users.user_id==user_id)
        .values(daily_limit=body.daily_limit, monthly_limit=body.monthly_limit)
    )
    await db.commit()
    return {"message": "✅ Limites mises à jour"}

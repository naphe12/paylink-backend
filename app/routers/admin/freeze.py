# app/routers/admin/freeze.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import admin_required
from app.services.security import freeze_user, unfreeze_user

router = APIRouter(prefix="/admin/users", tags=["admin:security"])

class FreezeBody(BaseModel):
    reason: str

class UnfreezeBody(BaseModel):
    note: str

@router.post("/{user_id}/freeze", dependencies=[Depends(admin_required)])
async def admin_freeze(user_id: str, body: FreezeBody, db: AsyncSession = Depends(get_db)):
    await freeze_user(db, user_id, body.reason)
    return {"message":"🔒 Compte gelé"}

@router.post("/{user_id}/unfreeze", dependencies=[Depends(admin_required)])
async def admin_unfreeze(user_id: str, body: UnfreezeBody, db: AsyncSession = Depends(get_db)):
    await unfreeze_user(db, user_id, body.note)
    return {"message":"✅ Compte réactivé"}

# app/routers/aml.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, condecimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import admin_required
from app.models.users import Users
from app.services.aml import update_risk_score
from pydantic import BaseModel, Field
from decimal import Decimal


router = APIRouter(prefix="/aml", tags=["aml"])

class AMLPayload(BaseModel):
    amount: Decimal = Field(gt=0)

    channel: str = "wallet"
    tx_id: str | None = None

@router.post("/score/{user_id}", dependencies=[Depends(admin_required)])
async def aml_score(user_id: str, body: AMLPayload, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(Users).where(Users.user_id==user_id))
    if not user: raise HTTPException(404, "Utilisateur introuvable")
    score = await update_risk_score(db, user, float(body.amount), body.channel)
    
    await db.commit()
    return {"user_id": user_id, "risk_score": score}

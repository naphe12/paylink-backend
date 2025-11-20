# app/routers/kyc.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db, get_current_user
from app.models import Users, KycVerifications  # à créer si pas encore
from datetime import datetime, timezone

router = APIRouter(prefix="/kyc", tags=["kyc"])

class KycInitiateIn(BaseModel):
    tier: str  # "BASIC" | "STANDARD" | "ENHANCED"

    @field_validator("tier")
    @classmethod
    def _v(cls, v):
        allowed = {"BASIC","STANDARD","ENHANCED"}
        if v not in allowed:
            raise ValueError(f"tier invalide, attendu: {allowed}")
        return v

class KycInitiateOut(BaseModel):
    kyc_id: str
    status: str
    required: list[str]

@router.post("/initiate", response_model=KycInitiateOut)
async def kyc_initiate(
    payload: KycInitiateIn,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user),
):
    # existe déjà ?
    existing = await db.scalar(
        select(KycVerifications).where(KycVerifications.user_id == user.user_id,
                                       KycVerifications.status.in_(["pending_docs","review"]))
    )
    if existing:
        return KycInitiateOut(
            kyc_id=str(existing.kyc_id),
            status=existing.status,
            required=existing.required_docs or [],
        )

    required_map = {
        "BASIC":    ["id_front", "selfie_liveness"],
        "STANDARD": ["id_front","id_back","selfie_liveness","proof_of_address"],
        "ENHANCED": ["id_front","id_back","selfie_liveness","proof_of_address","source_of_funds"]
    }
    required = required_map[payload.tier]

    res = await db.execute(insert(KycVerifications).values(
        user_id=user.user_id,
        tier=payload.tier,
        status="pending_docs",
        required_docs=required,
        collected_docs=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).returning(KycVerifications.kyc_id))
    (kyc_id,) = res.one()
    await db.commit()

    return KycInitiateOut(kyc_id=str(kyc_id), status="pending_docs", required=required)

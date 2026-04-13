# app/routers/admin/users_limits.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.database import get_db
from app.core.security import admin_required
from app.core.config import settings
from app.dependencies.step_up import require_admin_step_up
from app.models.users import Users
from pydantic import BaseModel, Field
from decimal import Decimal
from app.services.external_transfer_limits import (
    build_user_external_transfer_limit_analysis,
    normalize_external_transfer_limit_policy,
)


router = APIRouter(prefix="/admin/users", tags=["admin:users"])

class LimitsPayload(BaseModel):
    daily_limit: Decimal = Field(gt=0)
    monthly_limit: Decimal = Field(gt=0)


@router.get(
    "/{user_id}/external-transfer-limits/recommendation",
    dependencies=[Depends(admin_required)],
)
async def get_external_transfer_limits_recommendation(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    analysis = await build_user_external_transfer_limit_analysis(
        db,
        user_id=user.user_id,
        current_daily_limit=Decimal(str(getattr(user, "daily_limit", 0) or 0)),
        current_monthly_limit=Decimal(str(getattr(user, "monthly_limit", 0) or 0)),
        kyc_tier=int(getattr(user, "kyc_tier", 0) or 0),
        risk_score=int(getattr(user, "risk_score", 0) or 0),
    )
    recommendation = (analysis or {}).get("recommendation") or {}
    effective_policy = normalize_external_transfer_limit_policy(
        getattr(settings, "EXTERNAL_TRANSFER_LIMIT_POLICY", None)
    )
    current_daily = Decimal(str(getattr(user, "daily_limit", 0) or 0))
    current_monthly = Decimal(str(getattr(user, "monthly_limit", 0) or 0))
    recommended_daily = Decimal(str(recommendation.get("recommended_daily_limit") or 0))
    recommended_monthly = Decimal(str(recommendation.get("recommended_monthly_limit") or 0))
    effective_daily = current_daily
    effective_monthly = current_monthly
    if effective_policy == "dynamic":
        effective_daily = max(effective_daily, recommended_daily)
        effective_monthly = max(effective_monthly, recommended_monthly)

    return {
        "user_id": str(user.user_id),
        "policy_mode": effective_policy,
        "current_limits": {
            "daily_limit": str(current_daily),
            "monthly_limit": str(current_monthly),
        },
        "effective_limits": {
            "daily_limit": str(effective_daily),
            "monthly_limit": str(max(effective_monthly, effective_daily)),
        },
        **analysis,
    }



@router.patch(
    "/{user_id}/limits",
    dependencies=[Depends(admin_required), Depends(require_admin_step_up("admin_write"))],
)
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

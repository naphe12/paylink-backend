from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.utils.apply_kyc_limits import apply_kyc_limits


class KycDecision(BaseModel):
    reason: Optional[str] = None


router = APIRouter(prefix="/admin/kyc", tags=["Admin KYC"])


@router.get("/summary")
async def kyc_summary(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    rows = (
        await db.execute(
            select(Users.kyc_status, func.count(Users.user_id))
            .group_by(Users.kyc_status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    return {
        "pending": counts.get("pending", 0),
        "verified": counts.get("verified", 0),
        "rejected": counts.get("rejected", 0),
    }


@router.get("/pending")
async def pending_kyc(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(Users)
        .where(Users.kyc_status == "pending")
        .order_by(Users.kyc_submitted_at.desc())
    )
    applicants = (await db.execute(stmt)).scalars().all()

    return [
        {
            "user_id": str(u.user_id),
            "full_name": u.full_name,
            "email": u.email,
            "country": u.country_code,
            "kyc_tier": u.kyc_tier,
            "national_id_number": getattr(u, "national_id_number", None),
            "kyc_document_type": getattr(u, "kyc_document_type", None),
            "document_front_url": getattr(u, "document_front_url", None),
            "document_back_url": getattr(u, "document_back_url", None),
            "selfie_url": getattr(u, "selfie_url", None),
            "submitted_at": u.kyc_submitted_at.isoformat() if u.kyc_submitted_at else None,
        }
        for u in applicants
    ]


@router.post("/{user_id}/validate")
async def approve_kyc(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.get(Users, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    user.kyc_status = "verified"
    if not user.kyc_tier or user.kyc_tier < 1:
        user.kyc_tier = 1
    await apply_kyc_limits(user)
    if hasattr(user, "kyc_verified_at"):
        user.kyc_verified_at = datetime.utcnow()

    await db.commit()
    return {"message": "KYC validé"}


@router.post("/{user_id}/reject")
async def reject_kyc(
    user_id: str,
    decision: KycDecision,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.get(Users, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    user.kyc_status = "rejected"
    user.kyc_rejection_reason = decision.reason
    await db.commit()
    return {"message": "KYC rejeté", "reason": decision.reason}

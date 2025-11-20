from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.users import Users
from sqlalchemy import select

router = APIRouter(prefix="/kyc", tags=["KYC Admin"])

@router.post("/{user_id}/review")
async def review_kyc(
    user_id: str,
    status: str,           # "verified" ou "rejected"
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_user),
):
    if admin.role != "admin":
        raise HTTPException(403, "Accès refusé")

    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    user.kyc_status = status
    user.kyc_reject_reason = reason

    await db.commit()

    return {"message": f"KYC mis à jour → {status}"}

@router.get("/admin/kyc/pending")
async def list_pending_kyc(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    # Sécurité : seuls admins peuvent voir
    if current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")

    q = (
        select(Users)
        .where(Users.kyc_status == "pending")
    )
    rows = (await db.execute(q)).scalars().all()

    return [
        {
            "user_id": u.user_id,
            "full_name": u.full_name,
            "country": u.country_code,
            "national_id_number": u.national_id_number,
            "kyc_document_type": u.kyc_document_type,
            "document_front_url": u.document_front_url,
            "document_back_url": u.document_back_url,
            "selfie_url": u.selfie_url,
            "submitted_at": u.kyc_submitted_at.isoformat() if u.kyc_submitted_at else None,
        }
        for u in rows
    ]
@router.post("/admin/kyc/{user_id}/validate")
async def validate_kyc(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")

    user = await db.get(Users, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    user.kyc_status = "verified"
    user.kyc_tier = 1  # ✅ Montée automatique vers Tier 1

    apply_kyc_limits(user)

    await db.commit()
    return {"message": "✅ KYC Validé — Niveau 1 activé"}




@router.post("/admin/kyc/{user_id}/reject")
async def reject_kyc(
    user_id: str,
    reason: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")

    user = await db.get(Users, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    user.kyc_status = "rejected"
    user.kyc_rejection_reason = reason
    await db.commit()
    return {"message": "❌ KYC Rejeté", "reason": reason}


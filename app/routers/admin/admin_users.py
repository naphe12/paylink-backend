# app/routers/admin_users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.dependencies.auth import  get_current_admin
from app.models.users import Users
from app.websocket_manager import notify_user
from app.services.admin_notifications import push_admin_notification
from app.services.push_notifications import send_push_notification

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])

@router.get("")
@router.get("/")
async def list_users(
    q: str = "",
    status: str = "",
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    search = f"%{q.lower()}%"
    stmt = (
        select(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
            Users.kyc_status,
            Users.status,
            Users.risk_score,
        )
        .where(
            (Users.full_name.ilike(search))
            | (Users.email.ilike(search))
            | (Users.phone_e164.ilike(search))
        )
        .order_by(Users.created_at.desc())
        .limit(100)
    )
    if status:
        stmt = stmt.where(Users.status == status)
    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": str(r.user_id),
            "full_name": r.full_name,
            "email": r.email,
            "phone": r.phone_e164,
            "kyc_status": r.kyc_status,
            "status": r.status,
            "risk_score": r.risk_score,
        }
        for r in rows
    ]

@router.get("/{user_id}")
async def get_user_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    stmt = select(Users).where(Users.user_id == user_id)
    user = await db.scalar(stmt)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    return {
        "user_id": str(user.user_id),
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "phone_e164": user.phone_e164,
        "country_code": user.country_code,
        "role": user.role,
        "kyc_status": user.kyc_status,
        "kyc_tier": getattr(user, "kyc_tier", None),
        "kyc_reject_reason": getattr(user, "kyc_reject_reason", None),
        "status": user.status,
        "risk_score": user.risk_score,
        "daily_limit": float(getattr(user, "daily_limit", 0) or 0),
        "monthly_limit": float(getattr(user, "monthly_limit", 0) or 0),
        "used_daily": float(getattr(user, "used_daily", 0) or 0),
        "used_monthly": float(getattr(user, "used_monthly", 0) or 0),
        "credit_limit": float(getattr(user, "credit_limit", 0) or 0),
        "credit_used": float(getattr(user, "credit_used", 0) or 0),
        "email_verified": bool(getattr(user, "email_verified", False)),
        "email_verified_at": getattr(user, "email_verified_at", None),
        "last_seen": getattr(user, "last_seen", None),
        "created_at": getattr(user, "created_at", None),
        "updated_at": getattr(user, "updated_at", None),
        "external_transfers_blocked": getattr(user, "external_transfers_blocked", False),
    }

@router.post("/{user_id}/freeze")
async def freeze_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    await db.execute(
        update(Users)
        .where(Users.user_id == user_id)
        .values(status="frozen")
    )
    await db.commit()
    return {"message": "✅ Compte gelé"}

@router.post("/{user_id}/unfreeze")
async def unfreeze_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    await db.execute(
        update(Users)
        .where(Users.user_id == user_id)
        .values(status="active")
    )
    await db.commit()
    return {"message": "🔓 Compte réactivé"}

@router.post("/{user_id}/block-external")
async def block_external(user_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    await db.execute(update(Users).where(Users.user_id==user_id).values(external_transfers_blocked=True))
    await db.commit()
    return {"message": "🚫 Transferts externes bloqués"}

@router.post("/{user_id}/unblock-external")
async def unblock_external(user_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    await db.execute(update(Users).where(Users.user_id==user_id).values(external_transfers_blocked=False))
    await db.commit()
    return {"message": "✅ Transferts externes rétablis"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if getattr(user, "status", "") not in {"active", "suspended"}:
        raise HTTPException(
            status_code=400,
            detail="Suppression réservée aux comptes actifs ou suspendus.",
        )
    await db.execute(
        update(Users)
        .where(Users.user_id == user_id)
        .values(status="closed")
    )
    await db.commit()
    return {"message": "Utilisateur clôturé"}


@router.post("/{user_id}/request-kyc-upgrade")
async def request_kyc_upgrade(user_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    await notify_user(user_id, {
        "type": "KYC_UPGRADE_REQUIRED",
        "message": "Merci de completer votre KYC pour continuer a utiliser paylink."
    })
    await push_admin_notification(
        "kyc_reset",
        db=db,
        user_id=user_id,
        severity="info",
        title="Relance KYC envoyee",
        message=f"Nouvelle verification KYC demandee pour l'utilisateur {user_id}.",
        metadata={
            "admin_id": str(admin.user_id),
            "admin_email": admin.email,
        },
    )
    await send_push_notification(
        db,
        user_id=user_id,
        title="Action requise",
        body="Merci de mettre a jour vos informations KYC sur paylink.",
        data={"type": "kyc_action"},
    )
    return {"message": "Demande envoyee a l'utilisateur"}

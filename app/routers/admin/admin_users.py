# app/routers/admin_users.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import update, select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.dependencies.auth import  get_current_admin
from app.models.users import Users
from app.models.external_transfers import ExternalTransfers
from app.models.wallet_transactions import WalletTransactions
from app.models.agent_transactions import AgentTransactions
from app.schemas.users import UsersCreate, UsersRead
from app.services.user_provisioning import create_client_user
from app.services.wallet_service import ensure_user_financial_accounts
from app.websocket_manager import notify_user
from app.services.admin_notifications import push_admin_notification
from app.services.push_notifications import send_push_notification

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


class ResolveAmlLockBody(BaseModel):
    note: str | None = None
    raise_kyc_tier_to_one: bool = True
    reset_risk_score: bool = True


@router.post("/clients", response_model=UsersRead, status_code=status.HTTP_201_CREATED)
async def create_client_from_admin(
    payload: UsersCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        user = await create_client_user(db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(user)
    return UsersRead.model_validate(user, from_attributes=True)

@router.get("")
@router.get("/")
async def list_users(
    q: str = "",
    status: str = "",
    role: str = "",
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    search = f"%{q.lower()}%"
    last_external_transfer_at_sq = (
        select(func.max(ExternalTransfers.created_at))
        .where(ExternalTransfers.user_id == Users.user_id)
        .correlate(Users)
        .scalar_subquery()
    )
    last_wallet_activity_at_sq = (
        select(func.max(WalletTransactions.created_at))
        .where(WalletTransactions.user_id == Users.user_id)
        .correlate(Users)
        .scalar_subquery()
    )
    last_agent_activity_at_sq = (
        select(func.max(AgentTransactions.created_at))
        .where(AgentTransactions.client_user_id == Users.user_id)
        .correlate(Users)
        .scalar_subquery()
    )
    recent_activity_at = func.greatest(
        func.coalesce(last_external_transfer_at_sq, Users.created_at),
        func.coalesce(last_wallet_activity_at_sq, Users.created_at),
        func.coalesce(last_agent_activity_at_sq, Users.created_at),
        Users.created_at,
    )
    recent_activity_type = case(
        (
            func.coalesce(last_external_transfer_at_sq, Users.created_at)
            >= func.coalesce(last_wallet_activity_at_sq, Users.created_at),
            case(
                (
                    func.coalesce(last_external_transfer_at_sq, Users.created_at)
                    >= func.coalesce(last_agent_activity_at_sq, Users.created_at),
                    "transfer",
                ),
                else_="agent_operation",
            ),
        ),
        else_=case(
            (
                func.coalesce(last_wallet_activity_at_sq, Users.created_at)
                >= func.coalesce(last_agent_activity_at_sq, Users.created_at),
                "wallet_operation",
            ),
            else_="agent_operation",
        ),
    )
    stmt = (
        select(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
            Users.role,
            Users.kyc_status,
            Users.status,
            Users.risk_score,
            recent_activity_at.label("recent_activity_at"),
            recent_activity_type.label("recent_activity_type"),
        )
        .where(
            (Users.full_name.ilike(search))
            | (Users.email.ilike(search))
            | (Users.phone_e164.ilike(search))
        )
        .order_by(recent_activity_at.desc(), Users.created_at.desc())
        .limit(100)
    )
    if status:
        stmt = stmt.where(Users.status == status)
    if role:
        stmt = stmt.where(Users.role == role)
    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": str(r.user_id),
            "full_name": r.full_name,
            "email": r.email,
            "phone": r.phone_e164,
            "role": r.role,
            "kyc_status": r.kyc_status,
            "status": r.status,
            "risk_score": r.risk_score,
            "recent_activity_at": r.recent_activity_at,
            "recent_activity_type": r.recent_activity_type,
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


@router.post("/{user_id}/resolve-aml-lock")
async def resolve_aml_lock(
    user_id: str,
    body: ResolveAmlLockBody,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin)
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    updates = {
        "status": "active",
        "external_transfers_blocked": False,
    }
    if body.reset_risk_score:
        updates["risk_score"] = 0
    if body.raise_kyc_tier_to_one and int(getattr(user, "kyc_tier", 0) or 0) < 1:
        updates["kyc_tier"] = 1

    await db.execute(
        update(Users)
        .where(Users.user_id == user_id)
        .values(**updates)
    )
    await db.commit()
    await db.refresh(user)

    await push_admin_notification(
        "aml_high",
        db=db,
        user_id=user.user_id,
        severity="info",
        title="Blocage AML leve",
        message=f"Blocage AML leve manuellement pour {user.full_name or user.email}.",
        metadata={
            "admin_id": str(admin.user_id),
            "admin_email": admin.email,
            "note": body.note or "",
            "raise_kyc_tier_to_one": body.raise_kyc_tier_to_one,
            "reset_risk_score": body.reset_risk_score,
        },
    )

    return {
        "message": "Blocage AML leve",
        "user_id": str(user.user_id),
        "status": getattr(user, "status", None),
        "risk_score": int(getattr(user, "risk_score", 0) or 0),
        "kyc_tier": int(getattr(user, "kyc_tier", 0) or 0),
        "external_transfers_blocked": bool(getattr(user, "external_transfers_blocked", False)),
    }


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


@router.post("/{user_id}/repair-financial-accounts")
async def repair_user_financial_accounts(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    result = await ensure_user_financial_accounts(db, user=user)
    await db.commit()
    return {
        "message": "Provisioning financier repare",
        "user_id": str(user.user_id),
        "result": result,
    }

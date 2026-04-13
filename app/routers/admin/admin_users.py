# app/routers/admin_users.py
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import case, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.dependencies.step_up import get_admin_step_up_method, require_admin_step_up
from app.models.agent_transactions import AgentTransactions
from app.models.bonus_history import BonusHistory
from app.models.external_transfers import ExternalTransfers
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions
from app.models.wallets import Wallets
from app.schemas.users import UsersCreate, UsersRead
from app.services.admin_notifications import push_admin_notification
from app.services.audit_service import audit_log
from app.services.auth_sessions import get_request_ip, get_request_user_agent
from app.services.push_notifications import send_push_notification
from app.services.user_provisioning import create_client_user
from app.services.wallet_service import ensure_user_financial_accounts
from app.websocket_manager import notify_user

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


class ResolveAmlLockBody(BaseModel):
    note: str | None = None
    raise_kyc_tier_to_one: bool = True
    reset_risk_score: bool = True


class BonusCorrectionPreviewRequest(BaseModel):
    user_id: str
    scenario: str
    amount: Decimal
    reason: str
    note: str | None = None


def _user_admin_state(user: Users) -> dict:
    return {
        "status": str(getattr(user, "status", "") or ""),
        "external_transfers_blocked": bool(getattr(user, "external_transfers_blocked", False)),
        "risk_score": int(getattr(user, "risk_score", 0) or 0),
        "kyc_tier": int(getattr(user, "kyc_tier", 0) or 0),
    }


def _wallet_priority_case():
    return case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )


def _serialize_decimal(value: Decimal | None) -> float:
    return float(value or 0)


async def _get_primary_wallet(db: AsyncSession, user_id) -> Wallets | None:
    return await db.scalar(
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(_wallet_priority_case(), Wallets.wallet_id.asc())
        .limit(1)
    )


def _build_bonus_correction_preview(wallet: Wallets, payload: BonusCorrectionPreviewRequest) -> dict:
    scenario = str(payload.scenario or "").strip().lower()
    amount = Decimal(str(payload.amount or 0)).quantize(Decimal("0.01"))
    if amount <= Decimal("0"):
        raise HTTPException(status_code=400, detail="Montant bonus invalide.")
    reason = str(payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Motif obligatoire (min 3 caracteres).")

    bonus_before = Decimal(str(getattr(wallet, "bonus_balance", 0) or 0))
    if scenario == "credit_adjustment":
        signed_delta = amount
        source = "admin_credit"
        direction = "credit"
    elif scenario == "debit_adjustment":
        if bonus_before < amount:
            raise HTTPException(status_code=400, detail="Solde bonus insuffisant pour debiter.")
        signed_delta = -amount
        source = "admin_debit"
        direction = "debit"
    else:
        raise HTTPException(status_code=400, detail="Scenario non supporte.")

    bonus_after = bonus_before + signed_delta
    warnings: list[str] = []
    if bonus_after < Decimal("0"):
        warnings.append("Le solde bonus deviendra negatif.")

    return {
        "user_id": str(wallet.user_id) if wallet.user_id else None,
        "wallet_id": str(wallet.wallet_id),
        "scenario": scenario,
        "source": source,
        "direction": direction,
        "amount": _serialize_decimal(amount),
        "signed_delta": _serialize_decimal(signed_delta),
        "bonus_before": _serialize_decimal(bonus_before),
        "bonus_after": _serialize_decimal(bonus_after),
        "currency_code": "BIF",
        "reason": reason,
        "note": payload.note,
        "warnings": warnings,
        "can_apply": True,
    }


async def _audit_admin_user_action(
    *,
    db: AsyncSession,
    request: Request,
    admin: Users,
    user: Users,
    action: str,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    await audit_log(
        db,
        actor_user_id=str(getattr(admin, "user_id", "") or "") or None,
        actor_role=str(getattr(admin, "role", "") or "") or None,
        action=action,
        entity_type="user",
        entity_id=str(user.user_id),
        before_state=before_state,
        after_state={
            **(after_state or {}),
            "step_up_method": get_admin_step_up_method(request),
        },
        ip=get_request_ip(request),
        user_agent=get_request_user_agent(request),
    )


@router.post(
    "/clients",
    response_model=UsersRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_step_up("admin_write"))],
)
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
    exclude_wallet_currency: str = "",
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
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
    if exclude_wallet_currency:
        stmt = stmt.where(
            ~exists(
                select(Wallets.wallet_id).where(
                    Wallets.user_id == Users.user_id,
                    func.upper(Wallets.currency_code) == exclude_wallet_currency.upper(),
                )
            )
        )
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


@router.get("/bonus-balances")
async def list_users_bonus_balances(
    q: str = "",
    role: str = "client",
    status: str = "",
    min_bonus: float = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    safe_limit = max(1, min(int(limit or 200), 500))
    safe_min_bonus = max(float(min_bonus or 0), 0)
    search = f"%{q.lower()}%"
    bonus_total_expr = func.coalesce(func.sum(func.coalesce(Wallets.bonus_balance, 0)), 0)

    stmt = (
        select(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
            Users.role,
            Users.status,
            Users.kyc_status,
            bonus_total_expr.label("bonus_balance"),
            func.count(Wallets.wallet_id).label("wallet_count"),
        )
        .select_from(Users)
        .outerjoin(Wallets, Wallets.user_id == Users.user_id)
        .where(
            (Users.full_name.ilike(search))
            | (Users.email.ilike(search))
            | (Users.phone_e164.ilike(search))
        )
    )
    if role:
        stmt = stmt.where(Users.role == role)
    if status:
        stmt = stmt.where(Users.status == status)

    stmt = (
        stmt.group_by(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
            Users.role,
            Users.status,
            Users.kyc_status,
        )
        .having(bonus_total_expr >= safe_min_bonus)
        .order_by(bonus_total_expr.desc(), Users.created_at.desc())
        .limit(safe_limit)
    )

    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": str(r.user_id),
            "full_name": r.full_name,
            "email": r.email,
            "phone": r.phone_e164,
            "role": r.role,
            "status": r.status,
            "kyc_status": r.kyc_status,
            "bonus_balance": float(r.bonus_balance or 0),
            "bonus_currency": "BIF",
            "wallet_count": int(r.wallet_count or 0),
        }
        for r in rows
    ]


@router.get("/{user_id}")
async def get_user_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
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


@router.get("/{user_id}/bonus-balance")
async def get_user_bonus_balance(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    wallet = await _get_primary_wallet(db, user.user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable")
    return {
        "user_id": str(user.user_id),
        "full_name": user.full_name,
        "email": user.email,
        "phone_e164": user.phone_e164,
        "bonus_balance": _serialize_decimal(Decimal(str(getattr(wallet, "bonus_balance", 0) or 0))),
        "currency_code": "BIF",
        "wallet_id": str(wallet.wallet_id),
        "wallet_type": str(getattr(wallet, "type", "") or ""),
    }


@router.post("/bonus-corrections/preview")
async def preview_bonus_correction(
    payload: BonusCorrectionPreviewRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.scalar(select(Users).where(Users.user_id == payload.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    wallet = await _get_primary_wallet(db, user.user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable")
    preview = _build_bonus_correction_preview(wallet, payload)
    preview.update(
        {
            "full_name": user.full_name,
            "email": user.email,
            "wallet_type": str(getattr(wallet, "type", "") or ""),
        }
    )
    return preview


@router.post("/bonus-corrections/apply")
async def apply_bonus_correction(
    payload: BonusCorrectionPreviewRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.scalar(select(Users).where(Users.user_id == payload.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    wallet = await db.scalar(
        select(Wallets)
        .where(Wallets.user_id == user.user_id)
        .order_by(_wallet_priority_case(), Wallets.wallet_id.asc())
        .limit(1)
        .with_for_update()
    )
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable")

    preview = _build_bonus_correction_preview(wallet, payload)
    signed_delta = Decimal(str(preview["signed_delta"] or 0))
    wallet.bonus_balance = Decimal(str(getattr(wallet, "bonus_balance", 0) or 0)) + signed_delta

    reference = uuid4()
    history = BonusHistory(
        user_id=user.user_id,
        amount_bif=Decimal(str(preview["amount"] or 0)),
        source=preview["source"],
        reference_id=reference,
    )
    db.add(history)
    await db.commit()
    await db.refresh(wallet)

    return {
        "message": "Correction bonus appliquee.",
        "reference_id": str(reference),
        "preview": preview,
        "bonus_balance": _serialize_decimal(Decimal(str(getattr(wallet, "bonus_balance", 0) or 0))),
        "currency_code": "BIF",
        "user_id": str(user.user_id),
    }


@router.post("/{user_id}/freeze")
async def freeze_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_freeze")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    before_state = _user_admin_state(user)
    await db.execute(update(Users).where(Users.user_id == user_id).values(status="frozen"))
    await db.commit()
    await db.refresh(user)
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_FREEZE",
        before_state=before_state,
        after_state=_user_admin_state(user),
    )
    await db.commit()
    return {"message": "Compte gelé"}


@router.post("/{user_id}/unfreeze")
async def unfreeze_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_unfreeze")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    before_state = _user_admin_state(user)
    await db.execute(update(Users).where(Users.user_id == user_id).values(status="active"))
    await db.commit()
    await db.refresh(user)
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_UNFREEZE",
        before_state=before_state,
        after_state=_user_admin_state(user),
    )
    await db.commit()
    return {"message": "Compte réactivé"}


@router.post("/{user_id}/block-external")
async def block_external(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_external_transfer_block")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    before_state = _user_admin_state(user)
    await db.execute(update(Users).where(Users.user_id == user_id).values(external_transfers_blocked=True))
    await db.commit()
    await db.refresh(user)
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_EXTERNAL_TRANSFER_BLOCK",
        before_state=before_state,
        after_state=_user_admin_state(user),
    )
    await db.commit()
    return {"message": "Transferts externes bloqués"}


@router.post("/{user_id}/unblock-external")
async def unblock_external(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_external_transfer_unblock")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    before_state = _user_admin_state(user)
    await db.execute(update(Users).where(Users.user_id == user_id).values(external_transfers_blocked=False))
    await db.commit()
    await db.refresh(user)
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_EXTERNAL_TRANSFER_UNBLOCK",
        before_state=before_state,
        after_state=_user_admin_state(user),
    )
    await db.commit()
    return {"message": "Transferts externes rétablis"}


@router.post("/{user_id}/resolve-aml-lock")
async def resolve_aml_lock(
    user_id: str,
    body: ResolveAmlLockBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_aml_lock_resolve")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    before_state = _user_admin_state(user)

    updates = {
        "status": "active",
        "external_transfers_blocked": False,
    }
    if body.reset_risk_score:
        updates["risk_score"] = 0
    if body.raise_kyc_tier_to_one and int(getattr(user, "kyc_tier", 0) or 0) < 1:
        updates["kyc_tier"] = 1

    await db.execute(update(Users).where(Users.user_id == user_id).values(**updates))
    await db.commit()
    await db.refresh(user)
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_AML_LOCK_RESOLVE",
        before_state=before_state,
        after_state={
            **_user_admin_state(user),
            "note": body.note or "",
            "raise_kyc_tier_to_one": bool(body.raise_kyc_tier_to_one),
            "reset_risk_score": bool(body.reset_risk_score),
        },
    )

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
            "step_up_method": get_admin_step_up_method(request),
        },
    )
    await db.commit()

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
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_close")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if getattr(user, "status", "") not in {"active", "suspended"}:
        raise HTTPException(
            status_code=400,
            detail="Suppression réservée aux comptes actifs ou suspendus.",
        )
    before_state = _user_admin_state(user)
    await db.execute(update(Users).where(Users.user_id == user_id).values(status="closed"))
    await db.commit()
    await db.refresh(user)
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_CLOSE",
        before_state=before_state,
        after_state=_user_admin_state(user),
    )
    await db.commit()
    return {"message": "Utilisateur clôturé"}


@router.post("/{user_id}/request-kyc-upgrade")
async def request_kyc_upgrade(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_request_kyc_upgrade")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    before_state = _user_admin_state(user)
    await notify_user(
        str(user.user_id),
        {
            "type": "KYC_UPGRADE_REQUIRED",
            "message": "Merci de completer votre KYC pour continuer a utiliser paylink.",
        },
    )
    await push_admin_notification(
        "kyc_reset",
        db=db,
        user_id=str(user.user_id),
        severity="info",
        title="Relance KYC envoyee",
        message=f"Nouvelle verification KYC demandee pour l'utilisateur {user.user_id}.",
        metadata={
            "admin_id": str(admin.user_id),
            "admin_email": admin.email,
            "step_up_method": get_admin_step_up_method(request),
        },
    )
    await send_push_notification(
        db,
        user_id=str(user.user_id),
        title="Action requise",
        body="Merci de mettre a jour vos informations KYC sur paylink.",
        data={"type": "kyc_action"},
    )
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_REQUEST_KYC_UPGRADE",
        before_state=before_state,
        after_state=_user_admin_state(user),
    )
    await db.commit()
    return {"message": "Demande envoyee a l'utilisateur"}


@router.post("/{user_id}/repair-financial-accounts")
async def repair_user_financial_accounts(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("user_repair_financial_accounts")),
):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    before_state = _user_admin_state(user)

    result = await ensure_user_financial_accounts(db, user=user)
    await _audit_admin_user_action(
        db=db,
        request=request,
        admin=admin,
        user=user,
        action="ADMIN_USER_REPAIR_FINANCIAL_ACCOUNTS",
        before_state=before_state,
        after_state={**_user_admin_state(user), "repair_result": result},
    )
    await db.commit()
    return {
        "message": "Provisioning financier repare",
        "user_id": str(user.user_id),
        "result": result,
    }

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_accounts import BusinessAccounts
from app.models.business_members import BusinessMembers
from app.models.business_sub_wallet_movements import BusinessSubWalletMovements
from app.models.business_sub_wallets import BusinessSubWallets
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement

ALLOWED_MEMBER_ROLES = {"owner", "admin", "cashier", "viewer"}
ALLOWED_MEMBER_STATUSES = {"active", "inactive"}
ALLOWED_SUB_WALLET_STATUSES = {"active", "suspended"}


def _primary_wallet_stmt(user_id):
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
        .with_for_update()
    )


def _normalize_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _sub_wallet_remaining_capacity(*, current_amount: Decimal, spending_limit: Decimal) -> Decimal:
    limit = _normalize_decimal(spending_limit)
    current = _normalize_decimal(current_amount)
    remaining = limit - current
    return remaining if remaining > Decimal("0") else Decimal("0")


def _ensure_funding_within_limit(*, current_amount: Decimal, spending_limit: Decimal, amount: Decimal) -> None:
    if _normalize_decimal(amount) <= Decimal("0"):
        raise HTTPException(status_code=400, detail="Le montant doit etre strictement positif")
    remaining = _sub_wallet_remaining_capacity(
        current_amount=_normalize_decimal(current_amount),
        spending_limit=_normalize_decimal(spending_limit),
    )
    if _normalize_decimal(amount) > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"Plafond du sous-wallet depasse. Reste autorise: {remaining}",
        )


async def _serialize_sub_wallets(db: AsyncSession, business_id: UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(BusinessSubWallets, Users)
            .join(Users, Users.user_id == BusinessSubWallets.assigned_user_id, isouter=True)
            .where(BusinessSubWallets.business_id == business_id)
            .order_by(BusinessSubWallets.created_at.asc())
        )
    ).all()
    return [
        {
            "sub_wallet_id": item.sub_wallet_id,
            "business_id": item.business_id,
            "assigned_user_id": item.assigned_user_id,
            "assigned_label": (user.paytag or user.email or user.full_name) if user else None,
            "label": item.label,
            "currency_code": item.currency_code,
            "current_amount": Decimal(str(item.current_amount or 0)),
            "spending_limit": Decimal(str(item.spending_limit or 0)),
            "remaining_capacity": _sub_wallet_remaining_capacity(
                current_amount=Decimal(str(item.current_amount or 0)),
                spending_limit=Decimal(str(item.spending_limit or 0)),
            ),
            "status": item.status,
            "metadata": dict(item.metadata_ or {}),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item, user in rows
    ]


async def _serialize_business(db: AsyncSession, business: BusinessAccounts, *, current_user_id: UUID | None = None) -> dict:
    members = (
        await db.execute(
            select(BusinessMembers, Users)
            .join(Users, Users.user_id == BusinessMembers.user_id)
            .where(BusinessMembers.business_id == business.business_id)
            .order_by(BusinessMembers.created_at.asc())
        )
    ).all()
    sub_wallets = await _serialize_sub_wallets(db, business.business_id)
    return {
        "business_id": business.business_id,
        "owner_user_id": business.owner_user_id,
        "legal_name": business.legal_name,
        "display_name": business.display_name,
        "country_code": business.country_code,
        "is_active": business.is_active,
        "metadata": dict(business.metadata_ or {}),
        "created_at": business.created_at,
        "updated_at": business.updated_at,
        "current_membership_role": next(
            (member.role for member, _user in members if current_user_id and member.user_id == current_user_id),
            None,
        ),
        "members": [
            {
                "membership_id": member.membership_id,
                "business_id": member.business_id,
                "user_id": member.user_id,
                "role": member.role,
                "status": member.status,
                "metadata": dict(member.metadata_ or {}),
                "created_at": member.created_at,
                "member_label": user.paytag or user.email or user.full_name,
            }
            for member, user in members
        ],
        "sub_wallets": sub_wallets,
    }


async def _require_business_membership(
    db: AsyncSession,
    *,
    current_user: Users,
    business_id: UUID,
    allowed_roles: tuple[str, ...],
    require_active: bool = True,
) -> tuple[BusinessAccounts, BusinessMembers]:
    business = await db.get(BusinessAccounts, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Compte business introuvable")
    if require_active and not bool(business.is_active):
        raise HTTPException(status_code=403, detail="Compte business inactif")
    membership = await db.scalar(
        select(BusinessMembers).where(
            BusinessMembers.business_id == business_id,
            BusinessMembers.user_id == current_user.user_id,
            BusinessMembers.status == "active",
            BusinessMembers.role.in_(allowed_roles),
        )
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas gerer ce compte business")
    return business, membership


async def update_business_account_status(
    db: AsyncSession,
    *,
    current_user: Users,
    business_id: UUID,
    payload,
) -> dict:
    business, membership = await _require_business_membership(
        db,
        current_user=current_user,
        business_id=business_id,
        allowed_roles=("owner",),
        require_active=False,
    )
    if membership.user_id != business.owner_user_id:
        raise HTTPException(status_code=403, detail="Seul le proprietaire peut activer ou desactiver la structure")
    business.is_active = bool(payload.is_active)
    business.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _serialize_business(db, business, current_user_id=current_user.user_id)


async def create_business_account(db: AsyncSession, *, current_user: Users, payload) -> dict:
    item = BusinessAccounts(
        owner_user_id=current_user.user_id,
        legal_name=payload.legal_name.strip(),
        display_name=payload.display_name.strip(),
        country_code=payload.country_code,
    )
    db.add(item)
    await db.flush()
    db.add(
        BusinessMembers(
            business_id=item.business_id,
            user_id=current_user.user_id,
            role="owner",
            status="active",
        )
    )
    await db.commit()
    await db.refresh(item)
    return await _serialize_business(db, item, current_user_id=current_user.user_id)


async def list_my_business_accounts(db: AsyncSession, *, current_user: Users) -> list[dict]:
    businesses = (
        await db.execute(
            select(BusinessAccounts)
            .join(BusinessMembers, BusinessMembers.business_id == BusinessAccounts.business_id)
            .where(BusinessMembers.user_id == current_user.user_id)
            .order_by(BusinessAccounts.created_at.desc())
        )
    ).scalars().all()
    unique = []
    seen = set()
    for business in businesses:
        if business.business_id in seen:
            continue
        seen.add(business.business_id)
        unique.append(await _serialize_business(db, business, current_user_id=current_user.user_id))
    return unique


async def add_business_member(db: AsyncSession, *, current_user: Users, business_id: UUID, payload) -> dict:
    business, _membership = await _require_business_membership(
        db,
        current_user=current_user,
        business_id=business_id,
        allowed_roles=("owner", "admin"),
    )

    role = str(payload.role or "").strip().lower()
    if role not in ALLOWED_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="Role invalide")

    identifier = str(payload.identifier or "").strip()
    user = await db.scalar(select(Users).where(or_(Users.email == identifier, Users.paytag == identifier)))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    existing = await db.scalar(
        select(BusinessMembers).where(
            BusinessMembers.business_id == business_id,
            BusinessMembers.user_id == user.user_id,
        )
    )
    if existing:
        existing.role = role
        existing.status = "active"
    else:
        db.add(
            BusinessMembers(
                business_id=business_id,
                user_id=user.user_id,
                role=role,
                status="active",
            )
        )

    business.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _serialize_business(db, business, current_user_id=current_user.user_id)


async def update_business_member(
    db: AsyncSession,
    *,
    current_user: Users,
    business_id: UUID,
    membership_id: UUID,
    payload,
) -> dict:
    business, membership = await _require_business_membership(
        db,
        current_user=current_user,
        business_id=business_id,
        allowed_roles=("owner", "admin"),
    )
    target = await db.scalar(
        select(BusinessMembers).where(
            BusinessMembers.business_id == business_id,
            BusinessMembers.membership_id == membership_id,
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail="Membre business introuvable")
    if target.role == "owner":
        raise HTTPException(status_code=400, detail="Le proprietaire ne peut pas etre modifie ici")

    next_role = str(payload.role or target.role or "").strip().lower()
    next_status = str(payload.status or target.status or "").strip().lower()
    if next_role not in ALLOWED_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="Role invalide")
    if next_role == "owner":
        raise HTTPException(status_code=400, detail="Le role owner ne peut pas etre attribue ici")
    if next_status not in ALLOWED_MEMBER_STATUSES:
        raise HTTPException(status_code=400, detail="Statut membre invalide")

    if membership.role == "admin" and target.role == "admin":
        raise HTTPException(status_code=403, detail="Un admin ne peut pas modifier un autre admin")

    target.role = next_role
    target.status = next_status
    business.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _serialize_business(db, business, current_user_id=current_user.user_id)


async def create_business_sub_wallet(db: AsyncSession, *, current_user: Users, business_id: UUID, payload) -> dict:
    business, _membership = await _require_business_membership(
        db,
        current_user=current_user,
        business_id=business_id,
        allowed_roles=("owner", "admin"),
    )
    assigned_user_id = payload.assigned_user_id
    if assigned_user_id is not None:
        member_exists = await db.scalar(
            select(BusinessMembers).where(
                BusinessMembers.business_id == business_id,
                BusinessMembers.user_id == assigned_user_id,
                BusinessMembers.status == "active",
            )
        )
        if not member_exists:
            raise HTTPException(status_code=400, detail="Le membre assigne doit appartenir au compte business")

    owner_wallet = await db.scalar(_primary_wallet_stmt(business.owner_user_id))
    currency_code = str((owner_wallet.currency_code if owner_wallet else None) or "EUR").upper()
    item = BusinessSubWallets(
        business_id=business_id,
        assigned_user_id=assigned_user_id,
        label=payload.label.strip(),
        currency_code=currency_code,
        current_amount=Decimal("0"),
        spending_limit=Decimal(str(payload.spending_limit or 0)),
        status="active",
    )
    db.add(item)
    business.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _serialize_business(db, business, current_user_id=current_user.user_id)


async def update_business_sub_wallet(
    db: AsyncSession,
    *,
    current_user: Users,
    sub_wallet_id: UUID,
    payload,
) -> dict:
    sub_wallet = await db.scalar(
        select(BusinessSubWallets).where(BusinessSubWallets.sub_wallet_id == sub_wallet_id).with_for_update()
    )
    if not sub_wallet:
        raise HTTPException(status_code=404, detail="Sous-wallet business introuvable")
    business, _membership = await _require_business_membership(
        db,
        current_user=current_user,
        business_id=sub_wallet.business_id,
        allowed_roles=("owner", "admin"),
    )

    payload_fields = getattr(payload, "model_fields_set", set())

    if "assigned_user_id" in payload_fields:
        if payload.assigned_user_id:
            member_exists = await db.scalar(
                select(BusinessMembers).where(
                    BusinessMembers.business_id == sub_wallet.business_id,
                    BusinessMembers.user_id == payload.assigned_user_id,
                    BusinessMembers.status == "active",
                )
            )
            if not member_exists:
                raise HTTPException(status_code=400, detail="Le membre assigne doit appartenir au compte business")
            sub_wallet.assigned_user_id = payload.assigned_user_id
        else:
            sub_wallet.assigned_user_id = None

    if payload.label is not None and str(payload.label).strip():
        sub_wallet.label = str(payload.label).strip()
    if payload.spending_limit is not None:
        next_limit = Decimal(str(payload.spending_limit))
        if next_limit < Decimal(str(sub_wallet.current_amount or 0)):
            raise HTTPException(
                status_code=400,
                detail="Le plafond ne peut pas etre inferieur au montant deja alloue",
            )
        sub_wallet.spending_limit = next_limit
    if payload.status is not None:
        next_status = str(payload.status or "").strip().lower()
        if next_status not in ALLOWED_SUB_WALLET_STATUSES:
            raise HTTPException(status_code=400, detail="Statut sous-wallet invalide")
        sub_wallet.status = next_status

    sub_wallet.updated_at = datetime.now(timezone.utc)
    business.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _serialize_business(db, business, current_user_id=current_user.user_id)


async def fund_business_sub_wallet(db: AsyncSession, *, current_user: Users, sub_wallet_id: UUID, payload) -> dict:
    sub_wallet = await db.scalar(
        select(BusinessSubWallets).where(BusinessSubWallets.sub_wallet_id == sub_wallet_id).with_for_update()
    )
    if not sub_wallet:
        raise HTTPException(status_code=404, detail="Sous-wallet business introuvable")
    if sub_wallet.status != "active":
        raise HTTPException(status_code=400, detail="Ce sous-wallet ne peut pas etre alimente")
    business, membership = await _require_business_membership(
        db,
        current_user=current_user,
        business_id=sub_wallet.business_id,
        allowed_roles=("owner",),
    )
    if membership.user_id != business.owner_user_id:
        raise HTTPException(status_code=403, detail="Seul le proprietaire peut financer un sous-wallet")

    owner_wallet = await db.scalar(_primary_wallet_stmt(business.owner_user_id))
    if not owner_wallet:
        raise HTTPException(status_code=404, detail="Wallet proprietaire introuvable")
    amount = Decimal(str(payload.amount))
    _ensure_funding_within_limit(
        current_amount=Decimal(str(sub_wallet.current_amount or 0)),
        spending_limit=Decimal(str(sub_wallet.spending_limit or 0)),
        amount=amount,
    )
    if Decimal(str(owner_wallet.available or 0)) < amount:
        raise HTTPException(status_code=400, detail="Solde insuffisant pour financer le sous-wallet")

    owner_wallet.available = Decimal(str(owner_wallet.available or 0)) - amount
    sub_wallet.current_amount = Decimal(str(sub_wallet.current_amount or 0)) + amount
    sub_wallet.updated_at = datetime.now(timezone.utc)
    business.updated_at = datetime.now(timezone.utc)
    db.add(
        BusinessSubWalletMovements(
            sub_wallet_id=sub_wallet.sub_wallet_id,
            actor_user_id=current_user.user_id,
            direction="in",
            amount=amount,
            currency_code=sub_wallet.currency_code,
            note=payload.note,
        )
    )
    movement = await log_wallet_movement(
        db,
        wallet=owner_wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="business_sub_wallet_fund",
        reference=str(sub_wallet.sub_wallet_id),
        description=f"Financement sous-wallet {sub_wallet.label}",
    )
    ledger = LedgerService(db)
    owner_wallet_account = await ledger.ensure_wallet_account(owner_wallet)
    sub_wallet_account = await ledger.ensure_system_account(
        code=f"BUSINESS_SUBWALLET_{sub_wallet.sub_wallet_id}",
        name=f"Sous-wallet business {sub_wallet.label}",
        currency_code=sub_wallet.currency_code,
        metadata={
            "kind": "business_sub_wallet",
            "sub_wallet_id": str(sub_wallet.sub_wallet_id),
            "business_id": str(sub_wallet.business_id),
        },
    )
    await ledger.post_journal(
        tx_id=None,
        description=f"Financement sous-wallet business {sub_wallet.label}",
        metadata={
            "operation": "business_sub_wallet_fund",
            "sub_wallet_id": str(sub_wallet.sub_wallet_id),
            "business_id": str(sub_wallet.business_id),
            "movement_id": str(movement.transaction_id) if movement else None,
        },
        entries=[
            LedgerLine(account=owner_wallet_account, direction="debit", amount=amount, currency_code=owner_wallet.currency_code),
            LedgerLine(account=sub_wallet_account, direction="credit", amount=amount, currency_code=sub_wallet.currency_code),
        ],
    )
    await db.commit()
    return await _serialize_business(db, business, current_user_id=current_user.user_id)


async def release_business_sub_wallet(db: AsyncSession, *, current_user: Users, sub_wallet_id: UUID, payload) -> dict:
    sub_wallet = await db.scalar(
        select(BusinessSubWallets).where(BusinessSubWallets.sub_wallet_id == sub_wallet_id).with_for_update()
    )
    if not sub_wallet:
        raise HTTPException(status_code=404, detail="Sous-wallet business introuvable")
    if sub_wallet.status != "active":
        raise HTTPException(status_code=400, detail="Ce sous-wallet ne peut pas etre recupere")
    business, membership = await _require_business_membership(
        db,
        current_user=current_user,
        business_id=sub_wallet.business_id,
        allowed_roles=("owner",),
    )
    if membership.user_id != business.owner_user_id:
        raise HTTPException(status_code=403, detail="Seul le proprietaire peut recuperer un sous-wallet")

    amount = Decimal(str(payload.amount))
    if Decimal(str(sub_wallet.current_amount or 0)) < amount:
        raise HTTPException(status_code=400, detail="Montant disponible insuffisant dans le sous-wallet")

    owner_wallet = await db.scalar(_primary_wallet_stmt(business.owner_user_id))
    if not owner_wallet:
        raise HTTPException(status_code=404, detail="Wallet proprietaire introuvable")

    sub_wallet.current_amount = Decimal(str(sub_wallet.current_amount or 0)) - amount
    sub_wallet.updated_at = datetime.now(timezone.utc)
    business.updated_at = datetime.now(timezone.utc)
    owner_wallet.available = Decimal(str(owner_wallet.available or 0)) + amount
    db.add(
        BusinessSubWalletMovements(
            sub_wallet_id=sub_wallet.sub_wallet_id,
            actor_user_id=current_user.user_id,
            direction="out",
            amount=amount,
            currency_code=sub_wallet.currency_code,
            note=payload.note,
        )
    )
    movement = await log_wallet_movement(
        db,
        wallet=owner_wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="credit",
        operation_type="business_sub_wallet_release",
        reference=str(sub_wallet.sub_wallet_id),
        description=f"Recuperation sous-wallet {sub_wallet.label}",
    )
    ledger = LedgerService(db)
    owner_wallet_account = await ledger.ensure_wallet_account(owner_wallet)
    sub_wallet_account = await ledger.ensure_system_account(
        code=f"BUSINESS_SUBWALLET_{sub_wallet.sub_wallet_id}",
        name=f"Sous-wallet business {sub_wallet.label}",
        currency_code=sub_wallet.currency_code,
        metadata={
            "kind": "business_sub_wallet",
            "sub_wallet_id": str(sub_wallet.sub_wallet_id),
            "business_id": str(sub_wallet.business_id),
        },
    )
    await ledger.post_journal(
        tx_id=None,
        description=f"Recuperation sous-wallet business {sub_wallet.label}",
        metadata={
            "operation": "business_sub_wallet_release",
            "sub_wallet_id": str(sub_wallet.sub_wallet_id),
            "business_id": str(sub_wallet.business_id),
            "movement_id": str(movement.transaction_id) if movement else None,
        },
        entries=[
            LedgerLine(account=sub_wallet_account, direction="debit", amount=amount, currency_code=sub_wallet.currency_code),
            LedgerLine(account=owner_wallet_account, direction="credit", amount=amount, currency_code=owner_wallet.currency_code),
        ],
    )
    await db.commit()
    return await _serialize_business(db, business, current_user_id=current_user.user_id)

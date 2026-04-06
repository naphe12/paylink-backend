from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pot_contributions import PotContributions
from app.models.pot_members import PotMembers
from app.models.pots import Pots
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement

VALID_POT_MODES = {"collection", "group_savings"}
VALID_MEMBER_STATUSES = {"active", "paused", "removed", "left"}


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


def _display_user(user: Users | None) -> str | None:
    if not user:
        return None
    return user.paytag or user.email or user.full_name


def _pot_mode(metadata: dict | None) -> str:
    mode = str((metadata or {}).get("pot_mode") or "collection").strip().lower()
    return mode if mode in VALID_POT_MODES else "collection"


async def _serialize_members(db: AsyncSession, pot_id: UUID) -> list[dict]:
    contribution_totals = {
        user_id: Decimal(str(total or 0))
        for user_id, total in (
            await db.execute(
                select(
                    PotContributions.user_id,
                    func.coalesce(func.sum(PotContributions.amount), 0),
                )
                .where(PotContributions.pot_id == pot_id)
                .group_by(PotContributions.user_id)
            )
        ).all()
    }
    rows = (
        await db.execute(
            select(PotMembers, Users)
            .join(Users, Users.user_id == PotMembers.user_id)
            .where(PotMembers.pot_id == pot_id)
            .order_by(PotMembers.created_at.asc())
        )
    ).all()
    items = []
    for member, user in rows:
        target_amount = Decimal(str(member.target_amount)) if member.target_amount is not None else None
        contributed_amount = contribution_totals.get(member.user_id, Decimal("0"))
        progress_percent = (
            float(min((contributed_amount / target_amount) * Decimal("100"), Decimal("100")))
            if target_amount and target_amount > 0
            else 0
        )
        items.append(
            {
                "membership_id": member.membership_id,
                "pot_id": member.pot_id,
                "user_id": member.user_id,
                "role": member.role,
                "status": member.status,
                "target_amount": target_amount,
                "contributed_amount": contributed_amount,
                "remaining_amount": max(target_amount - contributed_amount, Decimal("0")) if target_amount else None,
                "progress_percent": round(progress_percent, 2),
                "member_label": _display_user(user),
                "metadata": dict(member.metadata_ or {}),
                "created_at": member.created_at,
            }
        )
    return items


async def _get_member_record(db: AsyncSession, *, pot_id: UUID, user_id: UUID) -> PotMembers | None:
    return await db.scalar(
        select(PotMembers).where(
            PotMembers.pot_id == pot_id,
            PotMembers.user_id == user_id,
            PotMembers.status == "active",
        )
    )


async def _resolve_pot_access(db: AsyncSession, *, pot_id: UUID, current_user: Users) -> tuple[Pots, str]:
    pot = await db.scalar(select(Pots).where(Pots.pot_id == pot_id))
    if not pot:
        raise HTTPException(status_code=404, detail="Cagnotte introuvable")
    if pot.owner_user_id == current_user.user_id:
        return pot, "owner"
    membership = await _get_member_record(db, pot_id=pot_id, user_id=current_user.user_id)
    if membership:
        return pot, membership.role or "member"
    raise HTTPException(status_code=403, detail="Vous ne pouvez pas acceder a cette cagnotte")


async def _serialize_contributions(db: AsyncSession, pot_id: UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(PotContributions, Users)
            .join(Users, Users.user_id == PotContributions.user_id)
            .where(PotContributions.pot_id == pot_id)
            .order_by(PotContributions.created_at.desc())
        )
    ).all()
    return [
        {
            "contribution_id": contribution.contribution_id,
            "pot_id": contribution.pot_id,
            "user_id": contribution.user_id,
            "amount": Decimal(str(contribution.amount)),
            "currency_code": contribution.currency_code,
            "note": contribution.note,
            "source": contribution.source,
            "contributor_label": _display_user(user),
            "metadata": dict(contribution.metadata_ or {}),
            "created_at": contribution.created_at,
        }
        for contribution, user in rows
    ]


async def _serialize_pot(
    db: AsyncSession,
    pot: Pots,
    *,
    access_role: str,
    contributions: list[dict] | None = None,
) -> dict:
    current_amount = Decimal(str(pot.current_amount or 0))
    target_amount = Decimal(str(pot.target_amount or 0))
    progress = float(min((current_amount / target_amount) * Decimal("100"), Decimal("100"))) if target_amount > 0 else 0
    members = await _serialize_members(db, pot.pot_id)
    return {
        "pot_id": pot.pot_id,
        "owner_user_id": pot.owner_user_id,
        "title": pot.title,
        "description": pot.description,
        "currency_code": pot.currency_code,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "share_token": pot.share_token,
        "is_public": bool(pot.is_public),
        "deadline_at": pot.deadline_at,
        "status": pot.status,
        "metadata": dict(pot.metadata_ or {}),
        "created_at": pot.created_at,
        "updated_at": pot.updated_at,
        "progress_percent": round(progress, 2),
        "remaining_amount": max(target_amount - current_amount, Decimal("0")),
        "pot_mode": _pot_mode(pot.metadata_ or {}),
        "access_role": access_role,
        "members": members,
        "contributions": contributions or [],
    }


async def create_pot(db: AsyncSession, *, current_user: Users, payload) -> dict:
    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    pot_mode = str(payload.pot_mode or "collection").strip().lower()
    if pot_mode not in VALID_POT_MODES:
        raise HTTPException(status_code=400, detail="Mode de cagnotte invalide")

    item = Pots(
        owner_user_id=current_user.user_id,
        title=payload.title.strip(),
        description=payload.description,
        currency_code=str(wallet.currency_code or "").upper(),
        target_amount=payload.target_amount,
        current_amount=Decimal("0"),
        share_token=secrets.token_urlsafe(10),
        is_public=payload.is_public,
        deadline_at=payload.deadline_at,
        status="active",
        metadata_={"pot_mode": pot_mode},
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return await _serialize_pot(db, item, access_role="owner")


async def list_my_pots(db: AsyncSession, *, current_user: Users) -> list[dict]:
    rows = (
        await db.execute(
            select(Pots)
            .outerjoin(PotMembers, PotMembers.pot_id == Pots.pot_id)
            .where(
                or_(
                    Pots.owner_user_id == current_user.user_id,
                    (PotMembers.user_id == current_user.user_id) & (PotMembers.status == "active"),
                )
            )
            .order_by(Pots.created_at.desc())
        )
    ).scalars().all()
    unique = []
    seen = set()
    for pot in rows:
        if pot.pot_id in seen:
            continue
        seen.add(pot.pot_id)
        access_role = "owner" if pot.owner_user_id == current_user.user_id else "member"
        unique.append(await _serialize_pot(db, pot, access_role=access_role))
    return unique


async def get_pot_detail(db: AsyncSession, *, current_user: Users, pot_id: UUID) -> dict:
    pot, access_role = await _resolve_pot_access(db, pot_id=pot_id, current_user=current_user)
    contributions = await _serialize_contributions(db, pot_id)
    return await _serialize_pot(db, pot, access_role=access_role, contributions=contributions)


async def add_pot_member(db: AsyncSession, *, current_user: Users, pot_id: UUID, payload) -> dict:
    pot = await db.scalar(select(Pots).where(Pots.pot_id == pot_id))
    if not pot:
        raise HTTPException(status_code=404, detail="Cagnotte introuvable")
    if pot.owner_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le proprietaire peut gerer les membres")
    if _pot_mode(pot.metadata_ or {}) != "group_savings":
        raise HTTPException(status_code=400, detail="Cette cagnotte n'est pas en mode epargne de groupe")

    identifier = str(payload.identifier or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Identifiant membre obligatoire")
    user = await db.scalar(select(Users).where(or_(Users.email == identifier, Users.paytag == identifier)))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.user_id == pot.owner_user_id:
        raise HTTPException(status_code=400, detail="Le proprietaire fait deja partie de la cagnotte")

    existing = await db.scalar(
        select(PotMembers).where(PotMembers.pot_id == pot_id, PotMembers.user_id == user.user_id)
    )
    if existing:
        existing.status = "active"
        existing.target_amount = payload.target_amount
        existing.role = "member"
        existing.metadata_ = {
            **dict(existing.metadata_ or {}),
            "reactivated_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        db.add(
            PotMembers(
                pot_id=pot_id,
                user_id=user.user_id,
                role="member",
                status="active",
                target_amount=payload.target_amount,
            )
        )

    pot.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_pot_detail(db, current_user=current_user, pot_id=pot_id)


async def update_pot_member(
    db: AsyncSession,
    *,
    current_user: Users,
    pot_id: UUID,
    membership_id: UUID,
    payload,
) -> dict:
    pot = await db.scalar(select(Pots).where(Pots.pot_id == pot_id))
    if not pot:
        raise HTTPException(status_code=404, detail="Cagnotte introuvable")
    if pot.owner_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le proprietaire peut gerer les membres")
    if _pot_mode(pot.metadata_ or {}) != "group_savings":
        raise HTTPException(status_code=400, detail="Cette cagnotte n'est pas en mode epargne de groupe")

    member = await db.scalar(
        select(PotMembers)
        .where(PotMembers.pot_id == pot_id, PotMembers.membership_id == membership_id)
        .with_for_update()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")

    if payload.status is not None:
        next_status = str(payload.status or "").strip().lower()
        if next_status not in VALID_MEMBER_STATUSES:
            raise HTTPException(status_code=400, detail="Statut membre invalide")
        member.status = next_status
    if payload.target_amount is not None:
        member.target_amount = payload.target_amount

    metadata = dict(member.metadata_ or {})
    metadata["last_update"] = {
        "actor_user_id": str(current_user.user_id),
        "actor_role": current_user.role,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    member.metadata_ = metadata
    pot.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_pot_detail(db, current_user=current_user, pot_id=pot_id)


async def leave_pot(db: AsyncSession, *, current_user: Users, pot_id: UUID) -> dict:
    pot = await db.scalar(select(Pots).where(Pots.pot_id == pot_id))
    if not pot:
        raise HTTPException(status_code=404, detail="Cagnotte introuvable")
    if pot.owner_user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Le proprietaire ne peut pas quitter sa propre cagnotte")
    member = await db.scalar(
        select(PotMembers)
        .where(
            PotMembers.pot_id == pot_id,
            PotMembers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not member or member.status != "active":
        raise HTTPException(status_code=400, detail="Vous n'etes pas membre actif de cette cagnotte")

    member.status = "left"
    member.metadata_ = {
        **dict(member.metadata_ or {}),
        "left_at": datetime.now(timezone.utc).isoformat(),
    }
    pot.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "pot_id": str(pot_id)}


async def contribute_pot(db: AsyncSession, *, current_user: Users, pot_id: UUID, payload) -> dict:
    pot = await db.scalar(select(Pots).where(Pots.pot_id == pot_id).with_for_update())
    if not pot:
        raise HTTPException(status_code=404, detail="Cagnotte introuvable")
    if pot.status != "active":
        raise HTTPException(status_code=400, detail="Cagnotte non active")

    if pot.owner_user_id != current_user.user_id:
        membership = await _get_member_record(db, pot_id=pot_id, user_id=current_user.user_id)
        if not membership:
            raise HTTPException(status_code=403, detail="Vous ne pouvez pas contribuer a cette cagnotte")

    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    if str(wallet.currency_code or "").upper() != str(pot.currency_code or "").upper():
        raise HTTPException(status_code=400, detail="Devise incompatible")

    amount = Decimal(str(payload.amount))
    if Decimal(str(wallet.available or 0)) < amount:
        raise HTTPException(status_code=400, detail="Solde insuffisant")

    wallet.available = Decimal(str(wallet.available or 0)) - amount
    pot.current_amount = Decimal(str(pot.current_amount or 0)) + amount
    pot.updated_at = datetime.now(timezone.utc)
    if Decimal(str(pot.current_amount)) >= Decimal(str(pot.target_amount)):
        pot.status = "funded"

    contribution = PotContributions(
        pot_id=pot.pot_id,
        user_id=current_user.user_id,
        amount=amount,
        currency_code=pot.currency_code,
        note=payload.note,
        source="wallet",
        metadata_={"pot_mode": _pot_mode(pot.metadata_ or {})},
    )
    db.add(contribution)

    wallet_movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="pot_contribution",
        reference=str(pot.pot_id),
        description=f"Contribution cagnotte {pot.title}",
    )

    tx = Transactions(
        initiated_by=current_user.user_id,
        sender_wallet=wallet.wallet_id,
        receiver_wallet=wallet.wallet_id,
        amount=amount,
        currency_code=wallet.currency_code,
        channel="internal",
        status="succeeded",
        description=f"Contribution cagnotte {pot.title}",
    )
    db.add(tx)
    await db.flush()

    ledger = LedgerService(db)
    wallet_account = await ledger.ensure_wallet_account(wallet)
    pot_account = await ledger.ensure_system_account(
        code=f"POT_{pot.pot_id}",
        name=f"Cagnotte {pot.title}",
        currency_code=pot.currency_code,
        metadata={"kind": "pot", "pot_id": str(pot.pot_id), "user_id": str(current_user.user_id)},
    )
    metadata = {
        "operation": "pot_contribution",
        "pot_id": str(pot.pot_id),
        "user_id": str(current_user.user_id),
        "transaction_id": str(tx.tx_id),
        "pot_mode": _pot_mode(pot.metadata_ or {}),
    }
    if wallet_movement:
        metadata["wallet_movement_id"] = str(wallet_movement.transaction_id)
    await ledger.post_journal(
        tx_id=tx.tx_id,
        description=f"Contribution cagnotte {pot.title}",
        metadata=metadata,
        entries=[
            LedgerLine(account=wallet_account, direction="debit", amount=amount, currency_code=wallet.currency_code),
            LedgerLine(account=pot_account, direction="credit", amount=amount, currency_code=pot.currency_code),
        ],
    )

    await db.commit()
    return await get_pot_detail(db, current_user=current_user, pot_id=pot_id)


async def close_pot(db: AsyncSession, *, current_user: Users, pot_id: UUID) -> dict:
    pot = await db.scalar(select(Pots).where(Pots.pot_id == pot_id).with_for_update())
    if not pot:
        raise HTTPException(status_code=404, detail="Cagnotte introuvable")
    if pot.owner_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Seul le proprietaire peut cloturer la cagnotte")
    if pot.status != "closed":
        pot.status = "closed"
        pot.updated_at = datetime.now(timezone.utc)
        await db.commit()
    return await get_pot_detail(db, current_user=current_user, pot_id=pot_id)

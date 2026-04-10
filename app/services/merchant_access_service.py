from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_accounts import BusinessAccounts
from app.models.business_members import BusinessMembers
from app.models.merchant_orders import MerchantOrders
from app.models.merchant_profiles import MerchantProfiles
from app.models.merchant_refunds import MerchantRefunds
from app.models.merchant_stores import MerchantStores
from app.models.users import Users

READ_ROLES = {"owner", "admin", "cashier", "viewer"}
WRITE_ROLES = {"owner", "admin", "cashier"}


@dataclass(slots=True)
class MerchantActorContext:
    actor_type: Literal["user", "api", "admin"]
    business_id: UUID | None = None
    role: str | None = None
    user: Users | None = None
    api_key_id: UUID | None = None


async def _get_business(db: AsyncSession, business_id: UUID) -> BusinessAccounts:
    business = await db.get(BusinessAccounts, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Compte business introuvable")
    if not bool(business.is_active):
        raise HTTPException(status_code=403, detail="Compte business inactif")
    return business


async def _get_membership(db: AsyncSession, *, business_id: UUID, user_id: UUID) -> BusinessMembers | None:
    return await db.scalar(
        select(BusinessMembers).where(
            BusinessMembers.business_id == business_id,
            BusinessMembers.user_id == user_id,
            BusinessMembers.status == "active",
        )
    )


async def _get_merchant_for_business(db: AsyncSession, *, business_id: UUID) -> MerchantProfiles:
    merchant = await db.scalar(
        select(MerchantProfiles).where(MerchantProfiles.business_id == business_id)
    )
    if not merchant:
        raise HTTPException(status_code=404, detail="Profil marchand introuvable")
    if str(merchant.status or "").lower() not in {"active", "pending_review"}:
        raise HTTPException(status_code=403, detail="Profil marchand indisponible")
    return merchant


def _require_actor_business_scope(actor: MerchantActorContext) -> UUID:
    if not actor.business_id:
        raise HTTPException(status_code=403, detail="Scope business manquant")
    return actor.business_id


async def require_business_access(
    db: AsyncSession,
    *,
    actor: MerchantActorContext,
    business_id: UUID,
    write: bool,
) -> tuple[BusinessAccounts, str]:
    business = await _get_business(db, business_id)

    if actor.actor_type == "admin":
        return business, "admin"

    if actor.actor_type == "api":
        scoped_business_id = _require_actor_business_scope(actor)
        if scoped_business_id != business_id:
            raise HTTPException(status_code=403, detail="Acces business insuffisant")
        return business, "api"

    if actor.actor_type != "user" or actor.user is None:
        raise HTTPException(status_code=401, detail="Acteur invalide")

    membership = await _get_membership(
        db,
        business_id=business_id,
        user_id=actor.user.user_id,
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Acces business insuffisant")

    role = str(membership.role or "").strip().lower()
    allowed_roles = WRITE_ROLES if write else READ_ROLES
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Role business insuffisant")

    return business, role


async def require_store_access(
    db: AsyncSession,
    *,
    actor: MerchantActorContext,
    store_id: UUID,
    write: bool,
) -> MerchantStores:
    row = (
        await db.execute(
            select(MerchantStores, MerchantProfiles)
            .join(
                MerchantProfiles,
                MerchantProfiles.merchant_id == MerchantStores.merchant_id,
            )
            .where(MerchantStores.store_id == store_id)
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Point de vente introuvable")

    store, merchant = row
    await require_business_access(
        db,
        actor=actor,
        business_id=merchant.business_id,
        write=write,
    )
    return store


async def require_order_access(
    db: AsyncSession,
    *,
    actor: MerchantActorContext,
    order_id: UUID,
    write: bool = False,
) -> MerchantOrders:
    row = (
        await db.execute(
            select(MerchantOrders, MerchantProfiles)
            .join(
                MerchantProfiles,
                MerchantProfiles.merchant_id == MerchantOrders.merchant_id,
            )
            .where(MerchantOrders.order_id == order_id)
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Commande marchande introuvable")

    order, merchant = row
    await require_business_access(
        db,
        actor=actor,
        business_id=merchant.business_id,
        write=write,
    )
    return order


async def require_refund_access(
    db: AsyncSession,
    *,
    actor: MerchantActorContext,
    refund_id: UUID,
    write: bool = False,
) -> MerchantRefunds:
    row = (
        await db.execute(
            select(MerchantRefunds, MerchantProfiles)
            .join(
                MerchantProfiles,
                MerchantProfiles.merchant_id == MerchantRefunds.merchant_id,
            )
            .where(MerchantRefunds.refund_id == refund_id)
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Remboursement marchand introuvable")

    refund, merchant = row
    await require_business_access(
        db,
        actor=actor,
        business_id=merchant.business_id,
        write=write,
    )
    return refund


async def require_merchant_for_business(
    db: AsyncSession,
    *,
    actor: MerchantActorContext,
    business_id: UUID,
    write: bool,
) -> MerchantProfiles:
    await require_business_access(
        db,
        actor=actor,
        business_id=business_id,
        write=write,
    )
    return await _get_merchant_for_business(db, business_id=business_id)

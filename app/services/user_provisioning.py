from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user_auth import UserAuth
from app.models.users import Users
from app.schemas.users import UsersCreate
from app.services.wallet_service import ensure_user_financial_accounts


def _build_paytag(full_name: str | None) -> str | None:
    if not full_name:
        return None
    normalized = " ".join(str(full_name).strip().lower().split())
    if not normalized:
        return None
    return "@" + normalized.replace(" ", "_")


async def create_client_user(
    db: AsyncSession,
    *,
    payload: UsersCreate,
) -> Users:
    existing_user = await db.scalar(
        select(Users).where(
            or_(
                Users.email == payload.email,
                Users.phone_e164 == payload.phone_e164 if payload.phone_e164 else False,
            )
        )
    )
    if existing_user:
        if str(existing_user.email or "").lower() == str(payload.email).lower():
            raise ValueError("Email deja enregistre")
        raise ValueError("Telephone deja enregistre")

    user = Users(
        full_name=payload.full_name,
        email=payload.email,
        phone_e164=payload.phone_e164,
        country_code=payload.country_code,
        status="active",
        kyc_status="unverified",
        role="client",
        paytag=_build_paytag(payload.full_name),
    )
    db.add(user)
    await db.flush()

    auth_entry = UserAuth(
        user_id=user.user_id,
        password_hash=hash_password(payload.password),
        mfa_enabled=False,
    )
    db.add(auth_entry)

    await ensure_user_financial_accounts(db, user=user)
    await db.flush()
    return user

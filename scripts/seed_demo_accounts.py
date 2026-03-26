from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from passlib.context import CryptContext
from sqlalchemy import text


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass(frozen=True)
class SeedAccount:
    user_id: uuid.UUID
    full_name: str
    username: str
    email: str
    phone_e164: str
    role: str
    paytag: str
    password: str
    kyc_status: str = "verified"
    status: str = "active"
    email_verified: bool = True
    agent_id: uuid.UUID | None = None
    agent_display_name: str | None = None
    wallet_type: str = "consumer"
    wallet_currency: str = "EUR"


ACCOUNTS: tuple[SeedAccount, ...] = (
    SeedAccount(
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        full_name="Alice Demo",
        username="alice_demo",
        email="alice.demo@paylink.local",
        phone_e164="+25761000001",
        role="user",
        paytag="@alice_demo",
        password="Paylink123!",
    ),
    SeedAccount(
        user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        full_name="Bob Demo",
        username="bob_demo",
        email="bob.demo@paylink.local",
        phone_e164="+25761000002",
        role="user",
        paytag="@bob_demo",
        password="Paylink123!",
    ),
    SeedAccount(
        user_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        full_name="Carla Demo",
        username="carla_demo",
        email="carla.demo@paylink.local",
        phone_e164="+25761000003",
        role="user",
        paytag="@carla_demo",
        password="Paylink123!",
    ),
    SeedAccount(
        user_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        full_name="Agent Demo",
        username="agent_demo",
        email="agent.demo@paylink.local",
        phone_e164="+25761000010",
        role="agent",
        paytag="@agent_demo",
        password="Paylink123!",
        agent_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        agent_display_name="Agent Demo Bujumbura",
        wallet_type="agent",
        wallet_currency="BIF",
    ),
    SeedAccount(
        user_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        full_name="Admin Demo",
        username="admin_demo",
        email="admin.demo@paylink.local",
        phone_e164="+25761000020",
        role="admin",
        paytag="@admin_demo",
        password="Paylink123!",
        wallet_type="admin",
        wallet_currency="EUR",
    ),
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


async def ensure_country(session) -> None:
    await session.execute(
        text(
            """
            INSERT INTO paylink.countries (country_code, name, currency_code, phone_prefix)
            VALUES (:country_code, :name, :currency_code, :phone_prefix)
            ON CONFLICT (country_code) DO UPDATE
            SET name = EXCLUDED.name,
                currency_code = EXCLUDED.currency_code,
                phone_prefix = EXCLUDED.phone_prefix
            """
        ),
        {
            "country_code": "BI",
            "name": "Burundi",
            "currency_code": "BIF",
            "phone_prefix": "+257",
        },
    )


async def ensure_currencies(session) -> None:
    for currency_code, name, decimals in (
        ("BIF", "Burundian Franc", 0),
        ("EUR", "Euro", 2),
    ):
        await session.execute(
            text(
                """
                INSERT INTO paylink.currencies (currency_code, name, decimals)
                VALUES (CAST(:currency_code AS CHAR(3)), :name, :decimals)
                ON CONFLICT (currency_code) DO UPDATE
                SET name = EXCLUDED.name,
                    decimals = EXCLUDED.decimals
                """
            ),
            {
                "currency_code": currency_code,
                "name": name,
                "decimals": decimals,
            },
        )


async def upsert_user(session, account: SeedAccount) -> uuid.UUID:
    user_result = await session.execute(
        text(
            """
            INSERT INTO paylink.users (
                user_id,
                full_name,
                username,
                email,
                phone_e164,
                country_code,
                status,
                kyc_status,
                role,
                paytag,
                email_verified
            )
            VALUES (
                :user_id,
                :full_name,
                :username,
                :email,
                :phone_e164,
                :country_code,
                CAST(:status AS paylink.user_status),
                CAST(:kyc_status AS paylink.kyc_status),
                CAST(:role AS paylink.user_role),
                :paytag,
                :email_verified
            )
            ON CONFLICT (email) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                phone_e164 = EXCLUDED.phone_e164,
                country_code = EXCLUDED.country_code,
                status = EXCLUDED.status,
                kyc_status = EXCLUDED.kyc_status,
                role = EXCLUDED.role,
                paytag = EXCLUDED.paytag,
                email_verified = EXCLUDED.email_verified
            RETURNING user_id
            """
        ),
        {
            "user_id": account.user_id,
            "full_name": account.full_name,
            "username": account.username,
            "email": account.email,
            "phone_e164": account.phone_e164,
            "country_code": "BI",
            "status": account.status,
            "kyc_status": account.kyc_status,
            "role": account.role,
            "paytag": account.paytag,
            "email_verified": account.email_verified,
        },
    )
    actual_user_id = user_result.scalar_one()

    password_hash = hash_password(account.password)
    await session.execute(
        text(
            """
            INSERT INTO paylink.user_auth (user_id, password_hash, mfa_enabled)
            VALUES (:user_id, :password_hash, false)
            ON CONFLICT (user_id) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                mfa_enabled = EXCLUDED.mfa_enabled
            """
        ),
        {
            "user_id": actual_user_id,
            "password_hash": password_hash,
        },
    )

    await session.execute(
        text(
            """
            INSERT INTO paylink.wallets (
                user_id,
                type,
                currency_code,
                available,
                pending,
                bonus_balance
            )
            SELECT
                :user_id,
                CAST(:wallet_type AS paylink.wallet_type),
                CAST(:currency_code AS CHAR(3)),
                0,
                0,
                0
            WHERE NOT EXISTS (
                SELECT 1
                FROM paylink.wallets
                WHERE user_id = :user_id
                  AND type = CAST(:wallet_type AS paylink.wallet_type)
                  AND currency_code = CAST(:currency_code AS CHAR(3))
            )
            """
        ),
        {
            "user_id": actual_user_id,
            "wallet_type": account.wallet_type,
            "currency_code": account.wallet_currency,
        },
    )

    if account.role == "agent" and account.agent_id and account.agent_display_name:
        await session.execute(
            text(
                """
                INSERT INTO paylink.agents (
                    agent_id,
                    user_id,
                    display_name,
                    country_code,
                    active,
                    commission_rate,
                    email,
                    phone,
                    daily_limit_bif,
                    daily_used_bif
                )
                VALUES (
                    :agent_id,
                    :user_id,
                    :display_name,
                    :country_code,
                    true,
                    :commission_rate,
                    :email,
                    :phone,
                    :daily_limit_bif,
                    :daily_used_bif
                )
                ON CONFLICT (user_id) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    country_code = EXCLUDED.country_code,
                    active = EXCLUDED.active,
                    commission_rate = EXCLUDED.commission_rate,
                    email = EXCLUDED.email,
                    phone = EXCLUDED.phone,
                    daily_limit_bif = EXCLUDED.daily_limit_bif,
                    daily_used_bif = EXCLUDED.daily_used_bif
                """
            ),
            {
                "agent_id": account.agent_id,
                "user_id": actual_user_id,
                "display_name": account.agent_display_name,
                "country_code": "BI",
                "commission_rate": "0.015",
                "email": account.email,
                "phone": account.phone_e164,
                "daily_limit_bif": "500000",
                "daily_used_bif": "0",
            },
        )

    return actual_user_id


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await ensure_country(session)
        await ensure_currencies(session)

        for account in ACCOUNTS:
            await upsert_user(session, account)

        await session.commit()

    print("Seed completed for demo accounts:")
    for account in ACCOUNTS:
        print(f"- {account.role:<5} {account.email} / {account.password}")


if __name__ == "__main__":
    asyncio.run(main())

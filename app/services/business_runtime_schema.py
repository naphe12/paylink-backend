from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_business_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_business",
        """
        CREATE TABLE IF NOT EXISTS product_business.business_accounts (
            business_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            legal_name text NOT NULL,
            display_name text NOT NULL,
            country_code text NULL,
            is_active boolean NOT NULL DEFAULT true,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_business.business_members (
            membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            business_id uuid NOT NULL REFERENCES product_business.business_accounts(business_id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            role text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_business.business_sub_wallets (
            sub_wallet_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            business_id uuid NOT NULL REFERENCES product_business.business_accounts(business_id) ON DELETE CASCADE,
            assigned_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            label text NOT NULL,
            currency_code text NOT NULL,
            current_amount numeric(20,6) NOT NULL DEFAULT 0,
            spending_limit numeric(20,6) NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'active',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_business.business_sub_wallet_movements (
            movement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            sub_wallet_id uuid NOT NULL REFERENCES product_business.business_sub_wallets(sub_wallet_id) ON DELETE CASCADE,
            actor_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            direction text NOT NULL,
            amount numeric(20,6) NOT NULL,
            currency_code text NOT NULL,
            note text NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_business_accounts_owner_created ON product_business.business_accounts (owner_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_business_members_business_created ON product_business.business_members (business_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_business_sub_wallets_business_created ON product_business.business_sub_wallets (business_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_business_sub_wallet_movements_wallet_created ON product_business.business_sub_wallet_movements (sub_wallet_id, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

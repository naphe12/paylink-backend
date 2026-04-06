from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_pots_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_pots",
        """
        CREATE TABLE IF NOT EXISTS product_pots.pots (
            pot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            title text NOT NULL,
            description text NULL,
            currency_code text NOT NULL,
            target_amount numeric(20,6) NOT NULL,
            current_amount numeric(20,6) NOT NULL DEFAULT 0,
            share_token text NULL UNIQUE,
            is_public boolean NOT NULL DEFAULT false,
            deadline_at timestamptz NULL,
            status text NOT NULL DEFAULT 'active',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_pots.pot_members (
            membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            pot_id uuid NOT NULL REFERENCES product_pots.pots(pot_id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            role text NOT NULL DEFAULT 'member',
            status text NOT NULL DEFAULT 'active',
            target_amount numeric(20,6) NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_pots.pot_contributions (
            contribution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            pot_id uuid NOT NULL REFERENCES product_pots.pots(pot_id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            amount numeric(20,6) NOT NULL,
            currency_code text NOT NULL,
            note text NULL,
            source text NOT NULL DEFAULT 'wallet',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pots_owner_created ON product_pots.pots (owner_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_pot_members_pot_created ON product_pots.pot_members (pot_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_pot_members_user_status ON product_pots.pot_members (user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_pot_contributions_pot_created ON product_pots.pot_contributions (pot_id, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

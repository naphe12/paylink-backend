from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_referrals_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_growth",
        """
        CREATE TABLE IF NOT EXISTS product_growth.referral_profiles (
            user_id uuid PRIMARY KEY REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            referral_code text NOT NULL UNIQUE,
            total_referrals integer NOT NULL DEFAULT 0,
            activated_referrals integer NOT NULL DEFAULT 0,
            rewards_earned numeric(20,6) NOT NULL DEFAULT 0,
            currency_code text NOT NULL DEFAULT 'BIF',
            is_active boolean NOT NULL DEFAULT true,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_growth.referral_rewards (
            reward_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            referrer_user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            referred_user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            status text NOT NULL DEFAULT 'pending',
            activation_reason text NULL,
            amount numeric(20,6) NOT NULL DEFAULT 0,
            currency_code text NOT NULL DEFAULT 'BIF',
            credited boolean NOT NULL DEFAULT false,
            activated_at timestamptz NULL,
            credited_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_referral_rewards_referrer_created ON product_growth.referral_rewards (referrer_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_referral_rewards_referred_created ON product_growth.referral_rewards (referred_user_id, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

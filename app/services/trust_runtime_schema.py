from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_trust_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_trust",
        """
        CREATE TABLE IF NOT EXISTS product_trust.trust_profiles (
            user_id uuid PRIMARY KEY REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            trust_score integer NOT NULL DEFAULT 0 CHECK (trust_score BETWEEN 0 AND 100),
            trust_level text NOT NULL DEFAULT 'new' CHECK (
                trust_level IN ('new','verified','trusted','premium_trusted','restricted')
            ),
            successful_payment_requests integer NOT NULL DEFAULT 0 CHECK (successful_payment_requests >= 0),
            successful_p2p_trades integer NOT NULL DEFAULT 0 CHECK (successful_p2p_trades >= 0),
            dispute_count integer NOT NULL DEFAULT 0 CHECK (dispute_count >= 0),
            failed_obligation_count integer NOT NULL DEFAULT 0 CHECK (failed_obligation_count >= 0),
            chargeback_like_count integer NOT NULL DEFAULT 0 CHECK (chargeback_like_count >= 0),
            kyc_verified boolean NOT NULL DEFAULT false,
            account_age_days integer NOT NULL DEFAULT 0 CHECK (account_age_days >= 0),
            last_computed_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_trust.trust_events (
            event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            source_type text NOT NULL,
            source_id text NULL,
            score_delta integer NOT NULL,
            reason_code text NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_trust.trust_badges (
            badge_code text PRIMARY KEY,
            name text NOT NULL,
            description text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_trust.user_trust_badges (
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            badge_code text NOT NULL REFERENCES product_trust.trust_badges(badge_code) ON DELETE RESTRICT,
            granted_at timestamptz NOT NULL DEFAULT now(),
            revoked_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (user_id, badge_code)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_trust_profiles_level_score ON product_trust.trust_profiles (trust_level, trust_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_trust_events_user_created ON product_trust.trust_events (user_id, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

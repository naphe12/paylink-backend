from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_savings_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_savings",
        """
        CREATE TABLE IF NOT EXISTS product_savings.savings_goals (
            goal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            title text NOT NULL,
            note text NULL,
            currency_code text NOT NULL,
            target_amount numeric(20,6) NOT NULL CHECK (target_amount > 0),
            current_amount numeric(20,6) NOT NULL DEFAULT 0 CHECK (current_amount >= 0),
            locked boolean NOT NULL DEFAULT false,
            target_date timestamptz NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_savings.savings_movements (
            movement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            goal_id uuid NOT NULL REFERENCES product_savings.savings_goals(goal_id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            amount numeric(20,6) NOT NULL CHECK (amount > 0),
            currency_code text NOT NULL,
            direction text NOT NULL CHECK (direction IN ('in','out')),
            source text NOT NULL,
            note text NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_savings_goals_user_status_created ON product_savings.savings_goals (user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_savings_movements_goal_created ON product_savings.savings_movements (goal_id, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

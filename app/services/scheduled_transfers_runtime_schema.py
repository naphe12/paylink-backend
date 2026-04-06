from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_scheduled_transfers_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_transfers",
        """
        CREATE TABLE IF NOT EXISTS product_transfers.scheduled_transfers (
            schedule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            receiver_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            receiver_identifier text NOT NULL,
            amount numeric(20,6) NOT NULL CHECK (amount > 0),
            currency_code text NOT NULL,
            frequency text NOT NULL CHECK (frequency IN ('daily','weekly','monthly')),
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','cancelled','completed','failed')),
            note text NULL,
            next_run_at timestamptz NOT NULL,
            last_run_at timestamptz NULL,
            last_result text NULL,
            remaining_runs integer NULL CHECK (remaining_runs IS NULL OR remaining_runs >= 0),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_user_status_created ON product_transfers.scheduled_transfers (user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_next_run ON product_transfers.scheduled_transfers (next_run_at)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

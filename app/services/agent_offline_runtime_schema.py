from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_agent_offline_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_agent_ops",
        """
        CREATE TABLE IF NOT EXISTS product_agent_ops.agent_offline_operations (
            operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            agent_id uuid NOT NULL REFERENCES paylink.agents(agent_id) ON DELETE CASCADE,
            client_user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            client_label text NOT NULL,
            operation_type text NOT NULL,
            amount numeric(14,2) NOT NULL,
            currency_code text NOT NULL,
            note text NULL,
            offline_reference text NOT NULL UNIQUE,
            status text NOT NULL DEFAULT 'queued',
            failure_reason text NULL,
            synced_response jsonb NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            queued_at timestamptz NOT NULL DEFAULT now(),
            synced_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT agent_offline_operations_type_valid CHECK (operation_type IN ('cash_in','cash_out')),
            CONSTRAINT agent_offline_operations_status_valid CHECK (status IN ('draft','queued','syncing','synced','failed','cancelled'))
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_offline_operations_agent_created ON product_agent_ops.agent_offline_operations (agent_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agent_offline_operations_agent_status_created ON product_agent_ops.agent_offline_operations (agent_user_id, status, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

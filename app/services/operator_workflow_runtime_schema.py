from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_operator_workflow_schema(db: AsyncSession) -> None:
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS paylink"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.operator_work_items (
              work_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              entity_type text NOT NULL,
              entity_id uuid NOT NULL,
              operator_status text NOT NULL DEFAULT 'needs_follow_up',
              owner_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
              blocked_reason text NULL,
              notes text NULL,
              follow_up_at timestamptz NULL,
              last_action_at timestamptz NOT NULL DEFAULT now(),
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT uq_operator_work_items_entity UNIQUE (entity_type, entity_id),
              CONSTRAINT ck_operator_work_items_status CHECK (
                operator_status IN ('needs_follow_up', 'blocked', 'watching', 'resolved')
              )
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_operator_work_items_status_follow_up
            ON paylink.operator_work_items (operator_status, follow_up_at, updated_at DESC)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_operator_work_items_entity
            ON paylink.operator_work_items (entity_type, entity_id)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_operator_work_items_owner
            ON paylink.operator_work_items (owner_user_id, updated_at DESC)
            """
        )
    )

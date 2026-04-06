from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_support_cases_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_support",
        """
        CREATE TABLE IF NOT EXISTS product_support.support_cases (
            case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            assigned_to_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            entity_type text NULL,
            entity_id text NULL,
            category text NOT NULL CHECK (
                category IN ('payment_request','wallet','p2p','escrow','cash_in','cash_out','kyc','fraud','other')
            ),
            subject text NOT NULL,
            description text NOT NULL,
            status text NOT NULL DEFAULT 'open' CHECK (
                status IN ('open','in_review','waiting_user','resolved','closed')
            ),
            priority text NOT NULL DEFAULT 'normal' CHECK (
                priority IN ('low','normal','high','urgent')
            ),
            reason_code text NULL,
            resolution_code text NULL,
            sla_due_at timestamptz NULL,
            first_response_at timestamptz NULL,
            resolved_at timestamptz NULL,
            closed_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_support.support_case_messages (
            message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL REFERENCES product_support.support_cases(case_id) ON DELETE CASCADE,
            author_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            author_role text NOT NULL,
            message_type text NOT NULL DEFAULT 'comment' CHECK (
                message_type IN ('comment','internal_note','status_update','system')
            ),
            body text NOT NULL,
            is_visible_to_customer boolean NOT NULL DEFAULT true,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_support.support_case_attachments (
            attachment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL REFERENCES product_support.support_cases(case_id) ON DELETE CASCADE,
            uploaded_by_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            file_name text NOT NULL,
            file_mime_type text NULL,
            file_size_bytes bigint NULL CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
            storage_key text NOT NULL,
            checksum_sha256 text NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_support.support_case_events (
            event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL REFERENCES product_support.support_cases(case_id) ON DELETE CASCADE,
            actor_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            actor_role text NULL,
            event_type text NOT NULL CHECK (
                event_type IN ('created','assigned','replied','status_changed','priority_changed','resolved','closed','reopened')
            ),
            before_status text NULL,
            after_status text NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_support_cases_user_status_created ON product_support.support_cases (user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_cases_assigned_status_created ON product_support.support_cases (assigned_to_user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_cases_entity ON product_support.support_cases (entity_type, entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_support_case_messages_case_created ON product_support.support_case_messages (case_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_case_attachments_case_created ON product_support.support_case_attachments (case_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_case_events_case_created ON product_support.support_case_events (case_id, created_at DESC)",
    ]

    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

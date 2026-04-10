from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_merchant_api_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_merchant_api",
        """
        CREATE TABLE IF NOT EXISTS product_merchant_api.merchant_api_keys (
            key_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            business_id uuid NOT NULL REFERENCES product_business.business_accounts(business_id) ON DELETE CASCADE,
            created_by_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            key_name text NOT NULL,
            key_prefix text NOT NULL,
            key_hash text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            last_used_at timestamptz NULL,
            revoked_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_api.merchant_webhooks (
            webhook_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            business_id uuid NOT NULL REFERENCES product_business.business_accounts(business_id) ON DELETE CASCADE,
            created_by_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            target_url text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            event_types jsonb NOT NULL DEFAULT '[]'::jsonb,
            signing_secret_hash text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            last_tested_at timestamptz NULL,
            revoked_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_api.merchant_webhook_events (
            event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            webhook_id uuid NOT NULL REFERENCES product_merchant_api.merchant_webhooks(webhook_id) ON DELETE CASCADE,
            business_id uuid NOT NULL REFERENCES product_business.business_accounts(business_id) ON DELETE CASCADE,
            event_type text NOT NULL,
            delivery_status text NOT NULL DEFAULT 'simulated',
            response_status_code integer NULL,
            request_signature text NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            response_body text NULL,
            attempt_count integer NOT NULL DEFAULT 0,
            last_attempted_at timestamptz NULL,
            next_retry_at timestamptz NULL,
            delivered_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE product_merchant_api.merchant_webhook_events ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0",
        "ALTER TABLE product_merchant_api.merchant_webhook_events ADD COLUMN IF NOT EXISTS last_attempted_at timestamptz NULL",
        "ALTER TABLE product_merchant_api.merchant_webhook_events ADD COLUMN IF NOT EXISTS next_retry_at timestamptz NULL",
        "CREATE INDEX IF NOT EXISTS idx_merchant_api_keys_business_created ON product_merchant_api.merchant_api_keys (business_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_webhooks_business_created ON product_merchant_api.merchant_webhooks (business_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_webhook_events_business_created ON product_merchant_api.merchant_webhook_events (business_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_webhook_events_status_retry ON product_merchant_api.merchant_webhook_events (delivery_status, next_retry_at)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

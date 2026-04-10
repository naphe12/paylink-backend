from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_payment_requests_v2_schema(db: AsyncSession) -> None:
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS product_payments"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS product_payments.payment_requests (
              request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              requester_user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              payer_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
              requester_wallet_id uuid NOT NULL REFERENCES paylink.wallets(wallet_id) ON DELETE RESTRICT,
              payer_wallet_id uuid NULL REFERENCES paylink.wallets(wallet_id) ON DELETE SET NULL,
              related_tx_id uuid NULL REFERENCES paylink.transactions(tx_id) ON DELETE SET NULL,
              amount numeric(20,6) NOT NULL CHECK (amount > 0),
              currency_code char(3) NOT NULL,
              status text NOT NULL DEFAULT 'pending',
              channel text NOT NULL DEFAULT 'direct',
              title text NULL,
              note text NULL,
              share_token text NULL UNIQUE,
              due_at timestamptz NULL,
              expires_at timestamptz NULL,
              paid_at timestamptz NULL,
              declined_at timestamptz NULL,
              cancelled_at timestamptz NULL,
              last_reminder_at timestamptz NULL,
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT payment_requests_status_valid CHECK (
                status IN ('draft','pending','paid','declined','cancelled','expired')
              ),
              CONSTRAINT payment_requests_requester_payer_diff CHECK (
                payer_user_id IS NULL OR payer_user_id <> requester_user_id
              )
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS product_payments.payment_request_events (
              event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              request_id uuid NOT NULL REFERENCES product_payments.payment_requests(request_id) ON DELETE CASCADE,
              actor_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
              actor_role text NULL,
              event_type text NOT NULL,
              before_status text NULL,
              after_status text NULL,
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT payment_request_events_type_valid CHECK (
                event_type IN ('created','sent','viewed','reminder_sent','paid','declined','cancelled','expired')
              )
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS product_payments.payment_request_reminders (
              reminder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              request_id uuid NOT NULL REFERENCES product_payments.payment_requests(request_id) ON DELETE CASCADE,
              reminder_type text NOT NULL,
              status text NOT NULL DEFAULT 'queued',
              scheduled_for timestamptz NOT NULL,
              sent_at timestamptz NULL,
              failure_reason text NULL,
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT payment_request_reminders_type_valid CHECK (
                reminder_type IN ('manual','auto_due','auto_overdue')
              ),
              CONSTRAINT payment_request_reminders_status_valid CHECK (
                status IN ('queued','sent','failed','cancelled')
              )
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_payment_requests_requester_status_created
            ON product_payments.payment_requests (requester_user_id, status, created_at DESC)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_payment_requests_payer_status_created
            ON product_payments.payment_requests (payer_user_id, status, created_at DESC)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_payment_request_events_request_created
            ON product_payments.payment_request_events (request_id, created_at DESC)
            """
        )
    )

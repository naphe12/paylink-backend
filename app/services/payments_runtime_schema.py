from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_payments_runtime_schema(db: AsyncSession) -> None:
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS paylink"))

    await db.execute(
        text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'payment_intent_direction' AND n.nspname = 'paylink'
              ) THEN
                CREATE TYPE paylink.payment_intent_direction AS ENUM ('deposit');
              END IF;
            END $$;
            """
        )
    )
    await db.execute(
        text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'payment_intent_rail' AND n.nspname = 'paylink'
              ) THEN
                CREATE TYPE paylink.payment_intent_rail AS ENUM ('mobile_money', 'bank_transfer');
              END IF;
            END $$;
            """
        )
    )
    await db.execute(
        text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'payment_intent_status' AND n.nspname = 'paylink'
              ) THEN
                CREATE TYPE paylink.payment_intent_status AS ENUM ('created', 'pending_provider', 'settled', 'credited', 'failed', 'cancelled');
              END IF;
            END $$;
            """
        )
    )

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.payment_intents (
              intent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              wallet_id uuid NOT NULL REFERENCES paylink.wallets(wallet_id) ON DELETE CASCADE,
              direction paylink.payment_intent_direction NOT NULL,
              rail paylink.payment_intent_rail NOT NULL,
              status paylink.payment_intent_status NOT NULL DEFAULT 'created',
              provider_code text NOT NULL,
              provider_channel text NULL,
              amount numeric(20,6) NOT NULL,
              currency_code char(3) NOT NULL,
              merchant_reference text NOT NULL UNIQUE,
              provider_reference text NULL,
              payer_identifier text NULL,
              credited_tx_id uuid NULL,
              target_instructions jsonb NOT NULL DEFAULT '{}'::jsonb,
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              settled_at timestamptz NULL,
              credited_at timestamptz NULL,
              expires_at timestamptz NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.payment_events (
              event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              intent_id uuid NOT NULL REFERENCES paylink.payment_intents(intent_id) ON DELETE CASCADE,
              provider_code text NOT NULL,
              provider_event_type text NULL,
              external_event_id text NULL,
              provider_reference text NULL,
              status text NULL,
              reason_code text NULL,
              payload jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE paylink.payment_events
            ADD COLUMN IF NOT EXISTS reason_code text NULL
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_payment_intents_user_created_at
            ON paylink.payment_intents (user_id, created_at DESC)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_payment_intents_provider_reference
            ON paylink.payment_intents (provider_code, provider_reference)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_events_provider_event
            ON paylink.payment_events (
              provider_code,
              COALESCE(external_event_id, ''),
              COALESCE(provider_reference, ''),
              COALESCE(status, '')
            )
            """
        )
    )

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_merchant_payments_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_merchant_payments",
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_profiles (
            merchant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            business_id uuid NOT NULL REFERENCES product_business.business_accounts(business_id) ON DELETE CASCADE,
            public_name text NOT NULL,
            legal_name text NOT NULL,
            country_code char(2) NULL,
            settlement_wallet_id uuid NULL REFERENCES paylink.wallets(wallet_id) ON DELETE SET NULL,
            default_currency char(3) NULL,
            mcc text NULL,
            support_email text NULL,
            support_phone text NULL,
            status text NOT NULL DEFAULT 'draft',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_profiles_business_id_key UNIQUE (business_id),
            CONSTRAINT merchant_profiles_status_valid CHECK (status IN ('draft','pending_review','active','suspended','closed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_stores (
            store_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_profiles(merchant_id) ON DELETE CASCADE,
            code text NULL,
            name text NOT NULL,
            country_code char(2) NULL,
            city text NULL,
            address_line text NULL,
            status text NOT NULL DEFAULT 'active',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_stores_merchant_code_key UNIQUE (merchant_id, code),
            CONSTRAINT merchant_stores_status_valid CHECK (status IN ('active','paused','archived'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_terminals (
            terminal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_stores(store_id) ON DELETE CASCADE,
            label text NOT NULL,
            channel text NOT NULL DEFAULT 'qr',
            device_fingerprint text NULL,
            status text NOT NULL DEFAULT 'active',
            last_seen_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_terminals_store_label_key UNIQUE (store_id, label),
            CONSTRAINT merchant_terminals_channel_valid CHECK (channel IN ('qr','cashier','api','payment_link')),
            CONSTRAINT merchant_terminals_status_valid CHECK (status IN ('active','blocked','revoked'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_orders (
            order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_profiles(merchant_id) ON DELETE CASCADE,
            store_id uuid NULL REFERENCES product_merchant_payments.merchant_stores(store_id) ON DELETE SET NULL,
            terminal_id uuid NULL REFERENCES product_merchant_payments.merchant_terminals(terminal_id) ON DELETE SET NULL,
            channel text NOT NULL DEFAULT 'manual',
            merchant_reference text NOT NULL,
            external_reference text NULL,
            amount numeric(20,6) NOT NULL,
            currency_code char(3) NOT NULL,
            collected_amount numeric(20,6) NOT NULL DEFAULT 0,
            refunded_amount numeric(20,6) NOT NULL DEFAULT 0,
            customer_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            customer_label text NULL,
            description text NULL,
            status text NOT NULL DEFAULT 'created',
            due_at timestamptz NULL,
            expires_at timestamptz NULL,
            paid_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_orders_merchant_reference_key UNIQUE (merchant_id, merchant_reference),
            CONSTRAINT merchant_orders_amount_positive CHECK (amount > 0),
            CONSTRAINT merchant_orders_collected_non_negative CHECK (collected_amount >= 0),
            CONSTRAINT merchant_orders_refunded_non_negative CHECK (refunded_amount >= 0),
            CONSTRAINT merchant_orders_status_valid CHECK (status IN ('created','pending','paid','partially_refunded','refunded','expired','cancelled','failed')),
            CONSTRAINT merchant_orders_channel_valid CHECK (channel IN ('static_qr','dynamic_qr','payment_link','api','manual'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_qr_codes (
            qr_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_profiles(merchant_id) ON DELETE CASCADE,
            store_id uuid NULL REFERENCES product_merchant_payments.merchant_stores(store_id) ON DELETE SET NULL,
            terminal_id uuid NULL REFERENCES product_merchant_payments.merchant_terminals(terminal_id) ON DELETE SET NULL,
            order_id uuid NULL REFERENCES product_merchant_payments.merchant_orders(order_id) ON DELETE CASCADE,
            qr_type text NOT NULL,
            token text NOT NULL,
            fixed_amount numeric(20,6) NULL,
            currency_code char(3) NULL,
            label text NULL,
            status text NOT NULL DEFAULT 'active',
            template_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            expires_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_qr_codes_token_key UNIQUE (token),
            CONSTRAINT merchant_qr_codes_amount_positive CHECK (fixed_amount IS NULL OR fixed_amount > 0),
            CONSTRAINT merchant_qr_codes_type_valid CHECK (qr_type IN ('static','dynamic')),
            CONSTRAINT merchant_qr_codes_status_valid CHECK (status IN ('active','disabled','expired'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_payment_links (
            link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_profiles(merchant_id) ON DELETE CASCADE,
            order_id uuid NULL REFERENCES product_merchant_payments.merchant_orders(order_id) ON DELETE CASCADE,
            token text NOT NULL,
            mode text NOT NULL DEFAULT 'one_time',
            fixed_amount numeric(20,6) NULL,
            currency_code char(3) NULL,
            max_uses integer NULL,
            use_count integer NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'active',
            expires_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_payment_links_token_key UNIQUE (token),
            CONSTRAINT merchant_payment_links_amount_positive CHECK (fixed_amount IS NULL OR fixed_amount > 0),
            CONSTRAINT merchant_payment_links_use_count_non_negative CHECK (use_count >= 0),
            CONSTRAINT merchant_payment_links_max_uses_positive CHECK (max_uses IS NULL OR max_uses > 0),
            CONSTRAINT merchant_payment_links_mode_valid CHECK (mode IN ('one_time','reusable')),
            CONSTRAINT merchant_payment_links_status_valid CHECK (status IN ('active','disabled','expired'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_payment_attempts (
            attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_orders(order_id) ON DELETE CASCADE,
            payer_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            payer_wallet_id uuid NULL REFERENCES paylink.wallets(wallet_id) ON DELETE SET NULL,
            rail text NOT NULL,
            status text NOT NULL DEFAULT 'created',
            amount numeric(20,6) NOT NULL,
            currency_code char(3) NOT NULL,
            payment_intent_id uuid NULL REFERENCES paylink.payment_intents(intent_id) ON DELETE SET NULL,
            wallet_tx_id uuid NULL REFERENCES paylink.transactions(tx_id) ON DELETE SET NULL,
            provider_reference text NULL,
            failure_code text NULL,
            failure_reason text NULL,
            authorized_at timestamptz NULL,
            settled_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_payment_attempts_payment_intent_id_key UNIQUE (payment_intent_id),
            CONSTRAINT merchant_payment_attempts_wallet_tx_id_key UNIQUE (wallet_tx_id),
            CONSTRAINT merchant_payment_attempts_amount_positive CHECK (amount > 0),
            CONSTRAINT merchant_payment_attempts_rail_valid CHECK (rail IN ('wallet','mobile_money','bank_transfer','virtual_card','external')),
            CONSTRAINT merchant_payment_attempts_status_valid CHECK (status IN ('created','pending','authorized','settled','failed','cancelled','expired'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_refunds (
            refund_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_profiles(merchant_id) ON DELETE CASCADE,
            order_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_orders(order_id) ON DELETE CASCADE,
            attempt_id uuid NULL REFERENCES product_merchant_payments.merchant_payment_attempts(attempt_id) ON DELETE SET NULL,
            amount numeric(20,6) NOT NULL,
            currency_code char(3) NOT NULL,
            reason text NULL,
            status text NOT NULL DEFAULT 'created',
            refund_tx_id uuid NULL REFERENCES paylink.transactions(tx_id) ON DELETE SET NULL,
            provider_reference text NULL,
            completed_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT merchant_refunds_amount_positive CHECK (amount > 0),
            CONSTRAINT merchant_refunds_status_valid CHECK (status IN ('created','pending','completed','failed','cancelled'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_receipts (
            receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_orders(order_id) ON DELETE CASCADE,
            receipt_number text NOT NULL,
            snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            issued_at timestamptz NOT NULL DEFAULT now(),
            voided_at timestamptz NULL,
            CONSTRAINT merchant_receipts_order_id_key UNIQUE (order_id),
            CONSTRAINT merchant_receipts_receipt_number_key UNIQUE (receipt_number)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_merchant_payments.merchant_payment_events (
            event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id uuid NOT NULL REFERENCES product_merchant_payments.merchant_profiles(merchant_id) ON DELETE CASCADE,
            order_id uuid NULL REFERENCES product_merchant_payments.merchant_orders(order_id) ON DELETE CASCADE,
            attempt_id uuid NULL REFERENCES product_merchant_payments.merchant_payment_attempts(attempt_id) ON DELETE SET NULL,
            refund_id uuid NULL REFERENCES product_merchant_payments.merchant_refunds(refund_id) ON DELETE SET NULL,
            actor_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
            event_type text NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_merchant_profiles_business_created ON product_merchant_payments.merchant_profiles (business_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_stores_merchant_created ON product_merchant_payments.merchant_stores (merchant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_terminals_store_created ON product_merchant_payments.merchant_terminals (store_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_orders_merchant_status ON product_merchant_payments.merchant_orders (merchant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_orders_merchant_created ON product_merchant_payments.merchant_orders (merchant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_orders_store_created ON product_merchant_payments.merchant_orders (store_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_qr_codes_merchant_status ON product_merchant_payments.merchant_qr_codes (merchant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_payment_links_merchant_status ON product_merchant_payments.merchant_payment_links (merchant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_payment_attempts_order_status ON product_merchant_payments.merchant_payment_attempts (order_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_payment_attempts_payer_created ON product_merchant_payments.merchant_payment_attempts (payer_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_refunds_merchant_status ON product_merchant_payments.merchant_refunds (merchant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_refunds_order_created ON product_merchant_payments.merchant_refunds (order_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_payment_events_merchant_created ON product_merchant_payments.merchant_payment_events (merchant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_merchant_payment_events_event_type ON product_merchant_payments.merchant_payment_events (event_type)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

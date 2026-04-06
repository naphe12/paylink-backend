from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_virtual_cards_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_cards",
        """
        CREATE TABLE IF NOT EXISTS product_cards.virtual_cards (
            card_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            linked_wallet_id uuid NULL REFERENCES paylink.wallets(wallet_id) ON DELETE SET NULL,
            cardholder_name text NOT NULL,
            brand text NOT NULL DEFAULT 'visa',
            card_type text NOT NULL DEFAULT 'standard',
            currency_code text NOT NULL,
            masked_pan text NOT NULL,
            last4 text NOT NULL,
            exp_month integer NOT NULL,
            exp_year integer NOT NULL,
            spending_limit numeric(20,6) NOT NULL DEFAULT 0,
            spent_amount numeric(20,6) NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'active',
            frozen_at timestamptz NULL,
            cancelled_at timestamptz NULL,
            last_used_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT virtual_cards_type_valid CHECK (card_type IN ('standard','single_use')),
            CONSTRAINT virtual_cards_status_valid CHECK (status IN ('active','frozen','cancelled','consumed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS product_cards.virtual_card_transactions (
            card_tx_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            card_id uuid NOT NULL REFERENCES product_cards.virtual_cards(card_id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            merchant_name text NOT NULL,
            merchant_category text NULL,
            amount numeric(20,6) NOT NULL,
            currency_code text NOT NULL,
            status text NOT NULL,
            decline_reason text NULL,
            reference text NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT virtual_card_transactions_status_valid CHECK (status IN ('authorized','declined','reversed'))
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_virtual_cards_user_created ON product_cards.virtual_cards (user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_virtual_cards_status ON product_cards.virtual_cards (status)",
        "CREATE INDEX IF NOT EXISTS idx_virtual_card_transactions_card_created ON product_cards.virtual_card_transactions (card_id, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

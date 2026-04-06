from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_fx_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_fx",
        """
        CREATE TABLE IF NOT EXISTS product_fx.user_currency_preferences (
            user_id uuid PRIMARY KEY REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            display_currency varchar(5) NOT NULL,
            auto_convert_small_balances boolean NOT NULL DEFAULT false,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

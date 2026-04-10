from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_financial_insights_schema(db: AsyncSession) -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS product_finance",
        """
        CREATE TABLE IF NOT EXISTS product_finance.financial_budget_rules (
            rule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
            category text NOT NULL,
            limit_amount numeric(20,6) NOT NULL CHECK (limit_amount > 0),
            currency_code text NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_financial_budget_rules_user_category ON product_finance.financial_budget_rules (user_id, category)",
        "CREATE INDEX IF NOT EXISTS idx_financial_budget_rules_user_created ON product_finance.financial_budget_rules (user_id, created_at DESC)",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()

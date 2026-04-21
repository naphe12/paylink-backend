"""external transfer provider fields

Revision ID: 20260421_000005
Revises: 20260328_000004
Create Date: 2026-04-21 12:00:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260421_000005"
down_revision = "20260328_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE paylink.external_transfers
        ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'internal',
        ADD COLUMN IF NOT EXISTS provider_ref text NULL,
        ADD COLUMN IF NOT EXISTS provider_status text NOT NULL DEFAULT 'created',
        ADD COLUMN IF NOT EXISTS idempotency_key text NULL,
        ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS last_error text NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_transfers_provider_status
        ON paylink.external_transfers (provider, provider_status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_transfers_provider_ref
        ON paylink.external_transfers (provider_ref)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS paylink.idx_external_transfers_provider_ref")
    op.execute("DROP INDEX IF EXISTS paylink.idx_external_transfers_provider_status")
    op.execute(
        """
        ALTER TABLE paylink.external_transfers
        DROP COLUMN IF EXISTS last_error,
        DROP COLUMN IF EXISTS retry_count,
        DROP COLUMN IF EXISTS idempotency_key,
        DROP COLUMN IF EXISTS provider_status,
        DROP COLUMN IF EXISTS provider_ref,
        DROP COLUMN IF EXISTS provider
        """
    )


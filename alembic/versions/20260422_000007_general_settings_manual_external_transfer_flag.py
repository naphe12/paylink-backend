"""general settings manual external transfer flag

Revision ID: 20260422_000007
Revises: 20260421_000006
Create Date: 2026-04-22 10:00:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260422_000007"
down_revision = "20260421_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS paylink.general_settings
        ADD COLUMN IF NOT EXISTS manual_external_transfer boolean NOT NULL DEFAULT false
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS paylink.general_settings
        DROP COLUMN IF EXISTS manual_external_transfer
        """
    )


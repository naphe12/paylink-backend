"""fix malformed limit_usage limit_id column

Revision ID: 20260327_000003
Revises: 20260325_000002
Create Date: 2026-03-27 10:30:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260327_000003"
down_revision = "20260325_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'paylink'
                  AND table_name = 'limit_usage'
                  AND column_name = 'limit_id '
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'paylink'
                  AND table_name = 'limit_usage'
                  AND column_name = 'limit_id'
            ) THEN
                ALTER TABLE paylink.limit_usage
                RENAME COLUMN "limit_id " TO limit_id;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'paylink'
                  AND table_name = 'limit_usage'
                  AND column_name = 'limit_id'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'paylink'
                  AND table_name = 'limit_usage'
                  AND column_name = 'limit_id '
            ) THEN
                ALTER TABLE paylink.limit_usage
                RENAME COLUMN limit_id TO "limit_id ";
            END IF;
        END
        $$;
        """
    )

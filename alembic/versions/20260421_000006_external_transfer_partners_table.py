"""external transfer partners table

Revision ID: 20260421_000006
Revises: 20260421_000005
Create Date: 2026-04-21 12:40:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260421_000006"
down_revision = "20260421_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS paylink.external_transfer_partners (
          partner_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          partner_name text NOT NULL UNIQUE,
          provider text NOT NULL DEFAULT 'internal',
          is_active boolean NOT NULL DEFAULT true,
          display_order integer NOT NULL DEFAULT 100,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_transfer_partners_active_order
        ON paylink.external_transfer_partners (is_active, display_order, partner_name)
        """
    )
    op.execute(
        """
        INSERT INTO paylink.external_transfer_partners (partner_name, provider, is_active, display_order)
        VALUES
          ('Lumicash', 'internal', true, 10),
          ('Ecocash', 'internal', true, 20),
          ('eNoti', 'internal', true, 30),
          ('iHela', 'ihela', true, 40)
        ON CONFLICT (partner_name) DO UPDATE
        SET provider = EXCLUDED.provider,
            is_active = EXCLUDED.is_active,
            display_order = EXCLUDED.display_order,
            updated_at = now()
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS paylink.idx_external_transfer_partners_active_order")
    op.execute("DROP TABLE IF EXISTS paylink.external_transfer_partners")


"""baseline existing schema

Revision ID: 20260325_000001
Revises:
Create Date: 2026-03-25 20:30:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260325_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing databases are treated as the starting point.
    # Future schema changes must be captured in new migrations.
    pass


def downgrade() -> None:
    pass

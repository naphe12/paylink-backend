"""runtime technical tables

Revision ID: 20260325_000002
Revises: 20260325_000001
Create Date: 2026-03-25 20:55:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260325_000002"
down_revision = "20260325_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS paylink")
    op.execute("CREATE SCHEMA IF NOT EXISTS escrow")
    op.execute("CREATE SCHEMA IF NOT EXISTS p2p")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS paylink.telegram_chat_links (
          chat_id text PRIMARY KEY,
          user_id uuid NOT NULL UNIQUE REFERENCES paylink.users(user_id) ON DELETE CASCADE,
          linked_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS paylink.telegram_chat_states (
          chat_id text PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
          draft jsonb NULL,
          raw_message text NULL,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS paylink.auth_refresh_tokens (
          id bigserial PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
          token_hash text NOT NULL UNIQUE,
          csrf_token text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          last_used_at timestamptz NULL,
          revoked_at timestamptz NULL,
          replaced_by_token_hash text NULL,
          user_agent text NULL,
          ip_address text NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_user_id
        ON paylink.auth_refresh_tokens (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_expires_at
        ON paylink.auth_refresh_tokens (expires_at)
        """
    )
    op.execute(
        """
        ALTER TABLE paylink.idempotency_keys
        ADD COLUMN IF NOT EXISTS request_hash text
        """
    )
    op.execute(
        """
        ALTER TABLE paylink.idempotency_keys
        ADD COLUMN IF NOT EXISTS response_status integer
        """
    )
    op.execute(
        """
        ALTER TABLE paylink.idempotency_keys
        ADD COLUMN IF NOT EXISTS response_payload jsonb
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS paylink.request_metrics (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          method text NOT NULL,
          path text NOT NULL,
          status_code int NOT NULL,
          duration_ms numeric(12, 3) NOT NULL,
          request_id text NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_request_metrics_created_at
        ON paylink.request_metrics (created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_request_metrics_status
        ON paylink.request_metrics (status_code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_request_metrics_path
        ON paylink.request_metrics (path)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS paylink.idx_request_metrics_path")
    op.execute("DROP INDEX IF EXISTS paylink.idx_request_metrics_status")
    op.execute("DROP INDEX IF EXISTS paylink.idx_request_metrics_created_at")
    op.execute("DROP TABLE IF EXISTS paylink.request_metrics")
    op.execute(
        """
        ALTER TABLE paylink.idempotency_keys
        DROP COLUMN IF EXISTS response_payload
        """
    )
    op.execute(
        """
        ALTER TABLE paylink.idempotency_keys
        DROP COLUMN IF EXISTS response_status
        """
    )
    op.execute(
        """
        ALTER TABLE paylink.idempotency_keys
        DROP COLUMN IF EXISTS request_hash
        """
    )
    op.execute("DROP INDEX IF EXISTS paylink.idx_auth_refresh_tokens_expires_at")
    op.execute("DROP INDEX IF EXISTS paylink.idx_auth_refresh_tokens_user_id")
    op.execute("DROP TABLE IF EXISTS paylink.auth_refresh_tokens")
    op.execute("DROP TABLE IF EXISTS paylink.telegram_chat_states")
    op.execute("DROP TABLE IF EXISTS paylink.telegram_chat_links")

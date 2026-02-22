import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def _ensure_webhook_logs_schema(db: AsyncSession) -> None:
    # Keep compatibility with older deployments that created a narrower table shape.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS escrow.webhook_logs (
          id bigserial PRIMARY KEY,
          event_type text NOT NULL,
          tx_hash text,
          status text NOT NULL,
          attempts int NOT NULL DEFAULT 1,
          payload jsonb NOT NULL,
          error text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        ALTER TABLE escrow.webhook_logs
        ADD COLUMN IF NOT EXISTS order_id uuid
    """))
    await db.execute(text("""
        ALTER TABLE escrow.webhook_logs
        ADD COLUMN IF NOT EXISTS network text
    """))

async def log_webhook(
    db: AsyncSession,
    *,
    event_type: str,
    status: str,
    payload: dict,
    tx_hash: str | None = None,
    order_id: str | None = None,
    network: str | None = None,
    attempts: int = 1,
    error: str | None = None,
):
    await _ensure_webhook_logs_schema(db)
    await db.execute(text("""
        INSERT INTO escrow.webhook_logs
          (event_type, status, payload, tx_hash, order_id, network, attempts, error)
        VALUES
          (:event_type, :status, CAST(:payload AS jsonb), :tx_hash, CAST(:order_id AS uuid), :network, :attempts, :error)
    """), {
        "event_type": event_type,
        "status": status,
        "payload": json.dumps(payload),
        "tx_hash": tx_hash,
        "order_id": order_id,
        "network": network,
        "attempts": attempts,
        "error": error,
    })

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

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
    await db.execute(text("""
        INSERT INTO escrow.webhook_logs
          (event_type, status, payload, tx_hash, order_id, network, attempts, error)
        VALUES
          (:event_type, :status, CAST(:payload AS jsonb), :tx_hash, CAST(:order_id AS uuid), :network, :attempts, :error)
    """), {
        "event_type": event_type,
        "status": status,
        "payload": payload,
        "tx_hash": tx_hash,
        "order_id": order_id,
        "network": network,
        "attempts": attempts,
        "error": error,
    })

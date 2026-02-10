from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/backoffice/webhooks", tags=["Backoffice - Webhooks"])


@router.get("")
async def list_webhook_logs(limit: int = 200, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS escrow.webhook_logs (
              id bigserial PRIMARY KEY,
              event_type text NOT NULL,
              tx_hash text,
              status text NOT NULL,
              attempts int NOT NULL DEFAULT 0,
              payload jsonb NOT NULL,
              error text,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    rows = (
        await db.execute(
            text(
                """
                SELECT id, event_type, tx_hash, status, attempts, payload, error, created_at
                FROM escrow.webhook_logs
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).fetchall()
    return [dict(r._mapping) for r in rows]

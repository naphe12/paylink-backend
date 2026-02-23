from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.core.database import async_session_maker


DEFAULT_ETA_SECONDS = 300


async def estimate_remaining_time(order) -> int | None:
    if getattr(order, "funded_at", None) is None:
        return None

    async with async_session_maker() as db:
        res = await db.execute(
            text(
                """
                SELECT AVG(EXTRACT(EPOCH FROM (paid_out_at - funded_at))) AS avg_seconds
                FROM escrow.orders
                WHERE funded_at IS NOT NULL
                  AND paid_out_at IS NOT NULL
                  AND paid_out_at >= funded_at
                """
            )
        )
        row = res.first()
        avg_seconds = float(getattr(row, "avg_seconds", 0) or 0)
        if avg_seconds <= 0:
            avg_seconds = float(DEFAULT_ETA_SECONDS)

    elapsed_seconds = (datetime.now(timezone.utc) - order.funded_at).total_seconds()
    remaining_seconds = max(avg_seconds - elapsed_seconds, 0)
    return int(remaining_seconds)

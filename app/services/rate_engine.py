from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.escrow_trader import EscrowTrader
from app.models.escrow_order import EscrowOrder
from app.models.escrow_enums import EscrowOrderStatus

# si tu n'as pas de model SQLAlchemy pour trader_quotes, fais en SQL text() (plus rapide à intégrer).
from sqlalchemy import text

class RateEngine:
    @staticmethod
    async def pick_best_trader(db: AsyncSession, usdt_amount: float) -> dict:
        now = datetime.now(timezone.utc)
        rows = await db.execute(text("""
          SELECT q.trader_id, q.rate
          FROM escrow.trader_quotes q
          JOIN escrow.traders t ON t.id = q.trader_id
          WHERE t.active = true
            AND q.expires_at > :now
            AND q.min_amount_usdt <= :amt
            AND (q.max_amount_usdt IS NULL OR q.max_amount_usdt >= :amt)
          ORDER BY q.rate DESC
          LIMIT 1
        """), {"now": now, "amt": usdt_amount})
        row = rows.first()
        if not row:
            raise ValueError("No valid trader quote available")
        return {"trader_id": row[0], "rate": row[1]}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users

router = APIRouter(prefix="/backoffice/monitoring", tags=["Backoffice - Monitoring"])

@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")
    # volumes par statut + webhooks failed (24h) + unbalanced journals
    stats = await db.execute(text("""
      SELECT status, COUNT(*)::int AS count
      FROM escrow.orders
      GROUP BY status
    """))
    by_status = [dict(r._mapping) for r in stats.fetchall()]

    wh = await db.execute(text("""
      SELECT status, COUNT(*)::int AS count
      FROM escrow.webhook_logs
      WHERE created_at >= now() - interval '24 hours'
      GROUP BY status
    """))
    webhook = [dict(r._mapping) for r in wh.fetchall()]

    bad = await db.execute(text("""
      SELECT COUNT(*)::int FROM (
        SELECT journal_id
        FROM paylink.ledger_entries
        GROUP BY journal_id
        HAVING SUM(CASE WHEN direction='DEBIT' THEN amount ELSE 0 END)
            <> SUM(CASE WHEN direction='CREDIT' THEN amount ELSE 0 END)
      ) t
    """))

    return {
        "orders_by_status": by_status,
        "webhooks_24h": webhook,
        "unbalanced_journals": bad.scalar_one(),
    }

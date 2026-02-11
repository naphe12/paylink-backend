from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.security.rbac import require_admin_user

router = APIRouter(prefix="/backoffice/risk", tags=["Backoffice - Risk"])

@router.get("/summary")
async def risk_summary(db: AsyncSession = Depends(get_db), user=Depends(require_admin_user)):
    high = await db.execute(text("""
      SELECT user_id, MAX(score)::int AS max_score, COUNT(*)::int AS events
      FROM paylink.risk_decisions
      WHERE created_at >= now() - interval '7 days'
      GROUP BY user_id
      HAVING MAX(score) >= 80
      ORDER BY max_score DESC
      LIMIT 50
    """))
    high_users = [dict(r._mapping) for r in high.fetchall()]

    by_stage = await db.execute(text("""
      SELECT stage, decision, COUNT(*)::int AS count
      FROM paylink.risk_decisions
      WHERE created_at >= now() - interval '24 hours'
      GROUP BY stage, decision
      ORDER BY stage, decision
    """))
    stage_stats = [dict(r._mapping) for r in by_stage.fetchall()]

    pending_alerts = await db.execute(text("""
      SELECT COUNT(*)::int
      FROM paylink.alerts
      WHERE delivered = false
    """))
    pending_count = int(pending_alerts.scalar_one() or 0)

    return {
        "high_users_7d": high_users,
        "stage_stats_24h": stage_stats,
        "pending_alerts": pending_count,
    }

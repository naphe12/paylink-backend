from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.aml_case import AMLCase
from app.models.aml_hit import AMLHit
from app.models.p2p_trade import P2PTrade
from app.models.users import Users

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


@router.get("/summary")
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    aml_open = (
        await db.execute(
            select(func.count()).select_from(AMLCase).where(AMLCase.status == "OPEN")
        )
    ).scalar() or 0

    aml_hits_24h = (
        await db.execute(
            select(func.count())
            .select_from(AMLHit)
            .where(AMLHit.created_at >= text("now() - interval '24 hours'"))
        )
    ).scalar() or 0

    high_risk_trades = (
        await db.execute(
            select(func.count()).select_from(P2PTrade).where(P2PTrade.risk_score >= 80)
        )
    ).scalar() or 0

    total_trades_24h = (
        await db.execute(
            select(func.count())
            .select_from(P2PTrade)
            .where(P2PTrade.created_at >= text("now() - interval '24 hours'"))
        )
    ).scalar() or 0

    liquidity = {
        "TREASURY_BIF": None,
        "TREASURY_USDC": None,
        "TREASURY_USDT": None,
    }

    arb_24h = 0

    return {
        "aml_open_cases": aml_open,
        "aml_hits_24h": aml_hits_24h,
        "high_risk_trades": high_risk_trades,
        "total_trades_24h": total_trades_24h,
        "liquidity": liquidity,
        "arbitrage_executions_24h": arb_24h,
    }


@router.get("/timeseries")
async def dashboard_timeseries(
    days: int = 14,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    q = text(
        """
      WITH d AS (
        SELECT generate_series(
          date_trunc('day', now()) - (:days::int || ' days')::interval,
          date_trunc('day', now()),
          '1 day'::interval
        ) AS day
      ),
      trades AS (
        SELECT date_trunc('day', created_at) AS day,
               count(*) AS trades_count,
               avg(risk_score) AS avg_risk
        FROM p2p.trades
        WHERE created_at >= now() - (:days::int || ' days')::interval
        GROUP BY 1
      ),
      hits AS (
        SELECT date_trunc('day', created_at) AS day,
               count(*) AS hits_count
        FROM aml.hits
        WHERE created_at >= now() - (:days::int || ' days')::interval
        GROUP BY 1
      )
      SELECT d.day::date AS day,
             COALESCE(trades.trades_count,0) AS trades_count,
             COALESCE(hits.hits_count,0) AS hits_count,
             COALESCE(trades.avg_risk,0) AS avg_risk
      FROM d
      LEFT JOIN trades USING(day)
      LEFT JOIN hits USING(day)
      ORDER BY d.day;
    """
    )
    rows = (await db.execute(q, {"days": days})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/risk-heatmap")
async def risk_heatmap(
    days: int = 14,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    q = text(
        """
      WITH base AS (
        SELECT date_trunc('day', created_at)::date AS day,
               CASE
                 WHEN risk_score < 20 THEN '0-19'
                 WHEN risk_score < 40 THEN '20-39'
                 WHEN risk_score < 60 THEN '40-59'
                 WHEN risk_score < 80 THEN '60-79'
                 ELSE '80-100'
               END AS bucket,
               count(*) AS cnt
        FROM p2p.trades
        WHERE created_at >= now() - (:days::int || ' days')::interval
        GROUP BY 1,2
      )
      SELECT day, bucket, cnt
      FROM base
      ORDER BY day, bucket;
    """
    )
    rows = (await db.execute(q, {"days": days})).mappings().all()
    return [dict(r) for r in rows]

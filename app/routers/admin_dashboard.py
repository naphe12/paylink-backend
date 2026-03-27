import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.aml_case import AMLCase
from app.models.aml_hit import AMLHit
from app.models.p2p_trade import P2PTrade
from app.models.users import Users
from app.services.paylink_ledger_service import PaylinkLedgerService

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])
logger = logging.getLogger(__name__)


@router.get("/summary")
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    async def _safe_scalar(label: str, stmt, default=0):
        try:
            val = (await db.execute(stmt)).scalar()
            return val if val is not None else default
        except Exception:
            logger.exception("dashboard_summary: failed metric %s", label)
            return default

    async def _safe_balance(account_code: str, currency: str):
        try:
            return str(
                await PaylinkLedgerService.get_balance(
                    db,
                    account_code=account_code,
                    currency=currency,
                )
            )
        except Exception:
            logger.exception(
                "dashboard_summary: failed balance account=%s currency=%s",
                account_code,
                currency,
            )
            return None

    aml_open = await _safe_scalar(
        "aml_open",
        select(func.count()).select_from(AMLCase).where(AMLCase.status == "OPEN"),
        0,
    )
    aml_hits_24h = await _safe_scalar(
        "aml_hits_24h",
        select(func.count())
        .select_from(AMLHit)
        .where(AMLHit.created_at >= text("now() - interval '24 hours'")),
        0,
    )
    high_risk_trades = await _safe_scalar(
        "high_risk_trades",
        select(func.count()).select_from(P2PTrade).where(P2PTrade.risk_score >= 80),
        0,
    )
    total_trades_24h = await _safe_scalar(
        "total_trades_24h",
        select(func.count())
        .select_from(P2PTrade)
        .where(P2PTrade.created_at >= text("now() - interval '24 hours'")),
        0,
    )

    liquidity = {
        "TREASURY_BIF": await _safe_balance("TREASURY_BIF", "BIF"),
        "TREASURY_USDC": await _safe_balance("TREASURY_USDC", "USDC"),
        "TREASURY_USDT": await _safe_balance("TREASURY_USDT", "USDT"),
    }

    arb_24h = await _safe_scalar(
        "arb_24h",
        text(
            """
            SELECT COUNT(*)::int
            FROM paylink.audit_log
            WHERE created_at >= now() - interval '24 hours'
              AND action = 'ARBITRAGE_EXECUTED'
            """
        ),
        0,
    )

    pending_deposits = await _safe_scalar(
        "pending_deposits",
        text(
            """
            SELECT COUNT(*)::int
            FROM paylink.wallet_cash_requests
            WHERE lower(status::text) = 'pending'
              AND upper(type::text) = 'DEPOSIT'
            """
        ),
        0,
    )
    pending_withdraws = await _safe_scalar(
        "pending_withdraws",
        text(
            """
            SELECT COUNT(*)::int
            FROM paylink.wallet_cash_requests
            WHERE lower(status::text) = 'pending'
              AND upper(type::text) = 'WITHDRAW'
            """
        ),
        0,
    )
    pending_external_transfers = await _safe_scalar(
        "pending_external_transfers",
        text(
            """
            SELECT COUNT(*)::int
            FROM paylink.external_transfers
            WHERE lower(status) IN ('pending', 'initiated')
            """
        ),
        0,
    )

    return {
        "aml_open_cases": aml_open,
        "aml_hits_24h": aml_hits_24h,
        "high_risk_trades": high_risk_trades,
        "total_trades_24h": total_trades_24h,
        "liquidity": liquidity,
        "arbitrage_executions_24h": arb_24h,
        "pending_deposits": pending_deposits,
        "pending_withdraws": pending_withdraws,
        "pending_external_transfers": pending_external_transfers,
    }


@router.get("/timeseries")
async def dashboard_timeseries(
    days: int = 14,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    days = max(1, min(int(days), 365))
    q = text(
        f"""
      WITH d AS (
        SELECT generate_series(
          date_trunc('day', now()) - INTERVAL '{days} days',
          date_trunc('day', now()),
          '1 day'::interval
        ) AS day
      ),
      trades AS (
        SELECT date_trunc('day', created_at) AS day,
               count(*) AS trades_count,
               avg(risk_score) AS avg_risk
        FROM p2p.trades
        WHERE created_at >= now() - INTERVAL '{days} days'
        GROUP BY 1
      ),
      hits AS (
        SELECT date_trunc('day', created_at) AS day,
               count(*) AS hits_count
        FROM aml.hits
        WHERE created_at >= now() - INTERVAL '{days} days'
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
    rows = (await db.execute(q)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/risk-heatmap")
async def risk_heatmap(
    days: int = 14,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    days = max(1, min(int(days), 365))
    q = text(
        f"""
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
        WHERE created_at >= now() - INTERVAL '{days} days'
        GROUP BY 1,2
      )
      SELECT day, bucket, cnt
      FROM base
      ORDER BY day, bucket;
    """
    )
    rows = (await db.execute(q)).mappings().all()
    return [dict(r) for r in rows]

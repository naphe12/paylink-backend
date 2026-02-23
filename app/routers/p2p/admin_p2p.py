from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.core.database import get_db
from app.dependencies.auth import get_current_admin  # you already have it
from app.models.users import Users
from app.models.p2p_trade import P2PTrade
from app.models.p2p_enums import TradeStatus

router = APIRouter(prefix="/admin/p2p", tags=["Admin P2P"])

@router.get("/trades")
async def admin_list_trades(status: str | None = None, db: AsyncSession = Depends(get_db), me: Users = Depends(get_current_admin)):
    stmt = select(P2PTrade)
    if status:
        stmt = stmt.where(P2PTrade.status == TradeStatus(status))
    res = await db.execute(stmt.order_by(P2PTrade.created_at.desc()))
    return [t for t in res.scalars().all()]


@router.get("/disputes")
async def list_disputes(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    disputes: list[dict] = []

    # New P2P disputes table (schema p2p)
    p2p_rows = await db.execute(
        text(
            """
            SELECT
              d.dispute_id,
              d.trade_id,
              NULL::uuid AS tx_id,
              d.status::text AS status,
              d.reason,
              d.created_at,
              NULL::timestamptz AS updated_at,
              d.resolved_at,
              d.opened_by AS opened_by_user_id,
              uo.full_name AS opened_by_name,
              d.resolved_by AS resolved_by_user_id,
              ur.full_name AS resolved_by_name,
              d.resolution,
              NULL::text AS evidence_url,
              t.buyer_id,
              ub.full_name AS buyer_name,
              t.seller_id,
              us.full_name AS seller_name,
              t.token::text AS token,
              t.token_amount,
              t.price_bif_per_usd,
              t.bif_amount,
              t.payment_method::text AS payment_method,
              t.status::text AS trade_status,
              NULL::numeric AS tx_amount,
              NULL::text AS tx_currency
            FROM p2p.disputes d
            LEFT JOIN p2p.trades t ON t.trade_id = d.trade_id
            LEFT JOIN paylink.users uo ON uo.user_id = d.opened_by
            LEFT JOIN paylink.users ur ON ur.user_id = d.resolved_by
            LEFT JOIN paylink.users ub ON ub.user_id = t.buyer_id
            LEFT JOIN paylink.users us ON us.user_id = t.seller_id
            ORDER BY created_at DESC
            """
        )
    )
    for row in p2p_rows.mappings().all():
        disputes.append(
            {
                "dispute_id": str(row["dispute_id"]),
                "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
                "tx_id": str(row["tx_id"]) if row["tx_id"] else None,
                "status": row["status"],
                "reason": row["reason"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "resolved_at": row["resolved_at"],
                "opened_by_user_id": str(row["opened_by_user_id"]) if row["opened_by_user_id"] else None,
                "opened_by_name": row["opened_by_name"],
                "resolved_by_user_id": str(row["resolved_by_user_id"]) if row["resolved_by_user_id"] else None,
                "resolved_by_name": row["resolved_by_name"],
                "resolution": row["resolution"],
                "evidence_url": row["evidence_url"],
                "buyer_user_id": str(row["buyer_id"]) if row["buyer_id"] else None,
                "buyer_name": row["buyer_name"],
                "seller_user_id": str(row["seller_id"]) if row["seller_id"] else None,
                "seller_name": row["seller_name"],
                "token": row["token"],
                "token_amount": float(row["token_amount"]) if row["token_amount"] is not None else None,
                "price_bif_per_usd": float(row["price_bif_per_usd"]) if row["price_bif_per_usd"] is not None else None,
                "bif_amount": float(row["bif_amount"]) if row["bif_amount"] is not None else None,
                "payment_method": row["payment_method"],
                "trade_status": row["trade_status"],
                "tx_amount": float(row["tx_amount"]) if row["tx_amount"] is not None else None,
                "tx_currency": row["tx_currency"],
                "source": "p2p",
            }
        )

    # Legacy disputes table (schema paylink)
    legacy_rows = await db.execute(
        text(
            """
            SELECT
              d.dispute_id,
              NULL::uuid AS trade_id,
              d.tx_id,
              d.status::text AS status,
              d.reason,
              d.created_at,
              d.updated_at,
              NULL::timestamptz AS resolved_at,
              d.opened_by AS opened_by_user_id,
              uo.full_name AS opened_by_name,
              NULL::uuid AS resolved_by_user_id,
              NULL::text AS resolved_by_name,
              NULL::text AS resolution,
              d.evidence_url,
              NULL::uuid AS buyer_id,
              NULL::text AS buyer_name,
              NULL::uuid AS seller_id,
              NULL::text AS seller_name,
              NULL::text AS token,
              NULL::numeric AS token_amount,
              NULL::numeric AS price_bif_per_usd,
              NULL::numeric AS bif_amount,
              NULL::text AS payment_method,
              NULL::text AS trade_status,
              t.amount AS tx_amount,
              t.currency_code::text AS tx_currency
            FROM paylink.disputes d
            LEFT JOIN paylink.users uo ON uo.user_id = d.opened_by
            LEFT JOIN paylink.transactions t ON t.tx_id = d.tx_id
            ORDER BY created_at DESC
            """
        )
    )
    for row in legacy_rows.mappings().all():
        disputes.append(
            {
                "dispute_id": str(row["dispute_id"]),
                "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
                "tx_id": str(row["tx_id"]) if row["tx_id"] else None,
                "status": row["status"],
                "reason": row["reason"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "resolved_at": row["resolved_at"],
                "opened_by_user_id": str(row["opened_by_user_id"]) if row["opened_by_user_id"] else None,
                "opened_by_name": row["opened_by_name"],
                "resolved_by_user_id": str(row["resolved_by_user_id"]) if row["resolved_by_user_id"] else None,
                "resolved_by_name": row["resolved_by_name"],
                "resolution": row["resolution"],
                "evidence_url": row["evidence_url"],
                "buyer_user_id": str(row["buyer_id"]) if row["buyer_id"] else None,
                "buyer_name": row["buyer_name"],
                "seller_user_id": str(row["seller_id"]) if row["seller_id"] else None,
                "seller_name": row["seller_name"],
                "token": row["token"],
                "token_amount": float(row["token_amount"]) if row["token_amount"] is not None else None,
                "price_bif_per_usd": float(row["price_bif_per_usd"]) if row["price_bif_per_usd"] is not None else None,
                "bif_amount": float(row["bif_amount"]) if row["bif_amount"] is not None else None,
                "payment_method": row["payment_method"],
                "trade_status": row["trade_status"],
                "tx_amount": float(row["tx_amount"]) if row["tx_amount"] is not None else None,
                "tx_currency": row["tx_currency"],
                "source": "paylink",
            }
        )

    if status:
        wanted = status.strip().lower()
        disputes = [d for d in disputes if str(d.get("status", "")).lower() == wanted]

    disputes.sort(key=lambda d: d.get("created_at") or 0, reverse=True)
    return disputes


@router.get("/risk")
async def risk_dashboard(
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    high_risk_stmt = select(func.count()).where(P2PTrade.risk_score >= 80)
    high_risk = (await db.execute(high_risk_stmt)).scalar()

    total_stmt = select(func.count()).select_from(P2PTrade)
    total = (await db.execute(total_stmt)).scalar()

    avg_stmt = select(func.avg(P2PTrade.risk_score))
    avg = (await db.execute(avg_stmt)).scalar()

    return {
        "total_trades": total,
        "high_risk_trades": high_risk,
        "average_risk": float(avg or 0),
    }

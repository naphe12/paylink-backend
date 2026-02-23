from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.core.database import get_db
from app.dependencies.auth import get_current_admin  # you already have it
from app.models.users import Users
from app.models.p2p_trade import P2PTrade

router = APIRouter(prefix="/admin/p2p", tags=["Admin P2P"])

@router.get("/trades")
async def admin_list_trades(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    rows = await db.execute(
        text(
            """
            SELECT
              t.trade_id,
              t.offer_id,
              t.status::text AS status,
              t.created_at,
              t.updated_at,
              t.expires_at,
              t.token::text AS token,
              t.token_amount,
              t.price_bif_per_usd,
              t.bif_amount,
              t.payment_method::text AS payment_method,
              t.risk_score,
              t.flags,
              t.escrow_tx_hash,
              t.fiat_sent_at,
              t.fiat_confirmed_at,
              t.buyer_id,
              ub.full_name AS buyer_name,
              t.seller_id,
              us.full_name AS seller_name,
              o.side::text AS offer_side,
              o.user_id AS offer_owner_id,
              uo.full_name AS offer_owner_name,
              COALESCE(d.disputes_count, 0) AS disputes_count
            FROM p2p.trades t
            LEFT JOIN p2p.offers o ON o.offer_id = t.offer_id
            LEFT JOIN paylink.users ub ON ub.user_id = t.buyer_id
            LEFT JOIN paylink.users us ON us.user_id = t.seller_id
            LEFT JOIN paylink.users uo ON uo.user_id = o.user_id
            LEFT JOIN (
              SELECT trade_id, COUNT(*)::int AS disputes_count
              FROM p2p.disputes
              GROUP BY trade_id
            ) d ON d.trade_id = t.trade_id
            ORDER BY t.created_at DESC
            """
        )
    )
    trades = []
    for row in rows.mappings().all():
        item = {
            "trade_id": str(row["trade_id"]),
            "offer_id": str(row["offer_id"]) if row["offer_id"] else None,
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
            "token": row["token"],
            "token_amount": float(row["token_amount"]) if row["token_amount"] is not None else None,
            "price_bif_per_usd": float(row["price_bif_per_usd"]) if row["price_bif_per_usd"] is not None else None,
            "bif_amount": float(row["bif_amount"]) if row["bif_amount"] is not None else None,
            "payment_method": row["payment_method"],
            "risk_score": int(row["risk_score"]) if row["risk_score"] is not None else 0,
            "flags": list(row["flags"] or []),
            "escrow_tx_hash": row["escrow_tx_hash"],
            "fiat_sent_at": row["fiat_sent_at"],
            "fiat_confirmed_at": row["fiat_confirmed_at"],
            "buyer_user_id": str(row["buyer_id"]) if row["buyer_id"] else None,
            "buyer_name": row["buyer_name"],
            "seller_user_id": str(row["seller_id"]) if row["seller_id"] else None,
            "seller_name": row["seller_name"],
            "offer_side": row["offer_side"],
            "offer_owner_user_id": str(row["offer_owner_id"]) if row["offer_owner_id"] else None,
            "offer_owner_name": row["offer_owner_name"],
            "disputes_count": int(row["disputes_count"] or 0),
        }
        trades.append(item)

    if status:
        wanted = status.strip().upper()
        trades = [t for t in trades if str(t.get("status", "")).upper() == wanted]

    return trades


@router.get("/trades/{trade_id}")
async def admin_trade_detail(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    row = await db.execute(
        text(
            """
            SELECT
              t.trade_id,
              t.offer_id,
              t.status::text AS status,
              t.created_at,
              t.updated_at,
              t.expires_at,
              t.token::text AS token,
              t.token_amount,
              t.price_bif_per_usd,
              t.bif_amount,
              t.payment_method::text AS payment_method,
              t.risk_score,
              t.flags,
              t.escrow_network,
              t.escrow_deposit_addr,
              t.escrow_tx_hash,
              t.escrow_locked_at,
              t.fiat_sent_at,
              t.fiat_confirmed_at,
              t.buyer_id,
              ub.full_name AS buyer_name,
              t.seller_id,
              us.full_name AS seller_name,
              o.side::text AS offer_side,
              o.user_id AS offer_owner_id,
              uo.full_name AS offer_owner_name,
              COALESCE(d.disputes_count, 0) AS disputes_count
            FROM p2p.trades t
            LEFT JOIN p2p.offers o ON o.offer_id = t.offer_id
            LEFT JOIN paylink.users ub ON ub.user_id = t.buyer_id
            LEFT JOIN paylink.users us ON us.user_id = t.seller_id
            LEFT JOIN paylink.users uo ON uo.user_id = o.user_id
            LEFT JOIN (
              SELECT trade_id, COUNT(*)::int AS disputes_count
              FROM p2p.disputes
              GROUP BY trade_id
            ) d ON d.trade_id = t.trade_id
            WHERE t.trade_id = CAST(:trade_id AS uuid)
            """
        ),
        {"trade_id": trade_id},
    )
    data = row.mappings().first()
    if not data:
        raise HTTPException(status_code=404, detail="Trade not found")

    return {
        "trade_id": str(data["trade_id"]),
        "offer_id": str(data["offer_id"]) if data["offer_id"] else None,
        "status": data["status"],
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "expires_at": data["expires_at"],
        "token": data["token"],
        "token_amount": float(data["token_amount"]) if data["token_amount"] is not None else None,
        "price_bif_per_usd": float(data["price_bif_per_usd"]) if data["price_bif_per_usd"] is not None else None,
        "bif_amount": float(data["bif_amount"]) if data["bif_amount"] is not None else None,
        "payment_method": data["payment_method"],
        "risk_score": int(data["risk_score"]) if data["risk_score"] is not None else 0,
        "flags": list(data["flags"] or []),
        "escrow_network": data["escrow_network"],
        "escrow_deposit_addr": data["escrow_deposit_addr"],
        "escrow_tx_hash": data["escrow_tx_hash"],
        "escrow_locked_at": data["escrow_locked_at"],
        "fiat_sent_at": data["fiat_sent_at"],
        "fiat_confirmed_at": data["fiat_confirmed_at"],
        "buyer_user_id": str(data["buyer_id"]) if data["buyer_id"] else None,
        "buyer_name": data["buyer_name"],
        "seller_user_id": str(data["seller_id"]) if data["seller_id"] else None,
        "seller_name": data["seller_name"],
        "offer_side": data["offer_side"],
        "offer_owner_user_id": str(data["offer_owner_id"]) if data["offer_owner_id"] else None,
        "offer_owner_name": data["offer_owner_name"],
        "disputes_count": int(data["disputes_count"] or 0),
    }


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

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
            SELECT dispute_id, trade_id, NULL::uuid AS tx_id, status::text AS status, reason, created_at
            FROM p2p.disputes
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
                "source": "p2p",
            }
        )

    # Legacy disputes table (schema paylink)
    legacy_rows = await db.execute(
        text(
            """
            SELECT dispute_id, NULL::uuid AS trade_id, tx_id, status::text AS status, reason, created_at
            FROM paylink.disputes
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

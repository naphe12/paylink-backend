from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.dependencies.auth import get_current_admin  # you already have it
from app.models.users import Users
from app.models.p2p_dispute import P2PDispute
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
    stmt = select(P2PDispute)

    if status:
        stmt = stmt.where(P2PDispute.status == status)

    stmt = stmt.order_by(P2PDispute.created_at.desc())

    res = await db.execute(stmt)
    return list(res.scalars().all())


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

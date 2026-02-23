from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.aml_case import AMLCase
from app.models.aml_hit import AMLHit
from app.models.users import Users

router = APIRouter(prefix="/admin/aml", tags=["Admin AML"])


@router.get("/cases")
async def list_cases(
    status: str | None = "OPEN",
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    stmt = select(AMLCase)
    if status:
        stmt = stmt.where(AMLCase.status == status)
    if user_id:
        stmt = stmt.where(AMLCase.user_id == user_id)
    stmt = stmt.order_by(AMLCase.created_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/cases/{case_id}")
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    case = await db.scalar(select(AMLCase).where(AMLCase.case_id == case_id))
    if not case:
        raise HTTPException(404, "Case not found")
    hits = await db.execute(select(AMLHit).where(AMLHit.trade_id == case.trade_id))
    return {
        "case": case,
        "hits": list(hits.scalars().all()),
    }


@router.post("/cases/{case_id}/close")
async def close_case(
    case_id: str,
    resolution: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    case = await db.scalar(select(AMLCase).where(AMLCase.case_id == case_id))
    if not case:
        raise HTTPException(404, "Case not found")
    case.status = "CLOSED"
    case.reason = f"{case.reason or ''}\nClosed by {me.email}: {resolution}"
    await db.commit()
    return {"status": "CLOSED"}


@router.get("/hits")
async def list_hits(
    user_id: str | None = None,
    trade_id: str | None = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    stmt = select(AMLHit)
    if user_id:
        stmt = stmt.where(AMLHit.user_id == user_id)
    if trade_id:
        stmt = stmt.where(AMLHit.trade_id == trade_id)

    stmt = stmt.order_by(AMLHit.created_at.desc()).limit(min(limit, 500))
    res = await db.execute(stmt)
    return list(res.scalars().all())

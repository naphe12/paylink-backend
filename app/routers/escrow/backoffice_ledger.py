from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from db import get_db

router = APIRouter(prefix="/backoffice/ledger", tags=["Backoffice - Ledger"])

@router.get("/balances")
async def balances(db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("""
        SELECT * FROM paylink.v_ledger_balances_by_token
        ORDER BY account_code, token
    """))
    return [dict(r._mapping) for r in res.fetchall()]

@router.get("/t-accounts")
async def t_accounts(limit: int = 200, db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("""
        SELECT *
        FROM paylink.v_t_accounts
        ORDER BY occurred_at DESC
        LIMIT :limit
    """), {"limit": limit})
    return [dict(r._mapping) for r in res.fetchall()]

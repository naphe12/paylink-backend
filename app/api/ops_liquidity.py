from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin

router = APIRouter()


@router.get("/ops/liquidity/bif")
async def get_bif_liquidity(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    available_row = await db.execute(
        text(
            """
            SELECT COALESCE(balance, 0) AS available_bif
            FROM paylink.v_ledger_balances
            WHERE code = 'TREASURY_BIF'
              AND currency_code = 'BIF'
            LIMIT 1
            """
        )
    )
    available = float((available_row.first() or [0])[0] or 0)

    reserved_row = await db.execute(
        text(
            """
            SELECT COALESCE(SUM(amount_bif), 0) AS reserved_bif
            FROM payout.assignments
            WHERE status = 'ASSIGNED'
            """
        )
    )
    reserved = float((reserved_row.first() or [0])[0] or 0)

    return {
        "available_bif": available,
        "reserved_bif": reserved,
    }


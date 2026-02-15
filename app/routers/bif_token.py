from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.services.paylink_ledger_service import PaylinkLedgerService

router = APIRouter(prefix="/bif", tags=["BIF Token (Off-chain)"])


@router.post("/transfer")
async def bif_transfer(
    to_user_id: str,
    amount: Decimal,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_user),
):
    if amount <= 0:
        raise HTTPException(400, "amount must be > 0")

    # debit sender wallet, credit receiver wallet
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=None,
        description="BIF internal transfer",
        postings=[
            {
                "account_code": f"WALLET_BIF_{me.user_id}",
                "direction": "CREDIT",
                "amount": amount,
                "currency": "BIF",
            },
            {
                "account_code": f"WALLET_BIF_{to_user_id}",
                "direction": "DEBIT",
                "amount": amount,
                "currency": "BIF",
            },
        ],
    )
    await db.commit()
    return {"status": "OK"}

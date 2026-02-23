from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.services.wallet_service import (
    convert_usdc_to_bif,
    ensure_bif_wallet_account,
    ensure_usdc_wallet_account,
    get_usdc_balance,
)
from app.services.wallet_withdraw_service import request_usdc_withdrawal

router = APIRouter(prefix="/wallet", tags=["Wallet USDC"])


class ConvertUsdcToBifRequest(BaseModel):
    amount_usdc: Decimal = Field(..., gt=Decimal("0"))
    rate: Decimal | None = Field(default=None, gt=Decimal("0"))


class WithdrawUsdcRequest(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0"))
    to_address: str = Field(..., min_length=8, max_length=255)


@router.get("/usdc")
async def wallet_usdc(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        user_id = str(current_user.user_id)
        account_code = await ensure_usdc_wallet_account(user_id, db=db)
        balance = await get_usdc_balance(user_id, db=db)
        return {
            "currency": "USDC",
            "balance": float(balance),
            "account_code": account_code,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/convert")
async def wallet_convert(
    payload: ConvertUsdcToBifRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        user_id = str(current_user.user_id)
        await ensure_usdc_wallet_account(user_id, db=db)
        await ensure_bif_wallet_account(user_id, db=db)

        conversion = await convert_usdc_to_bif(
            user_id=user_id,
            amount_usdc=payload.amount_usdc,
            rate=payload.rate,
            ref=f"WALLET_CONVERT:{user_id}:{payload.amount_usdc.normalize()}",
            db=db,
        )
        await db.commit()
        return {
            "status": "OK",
            "converted_bif": float(conversion["amount_bif"]),
            "amount_usdc": float(conversion["amount_usdc"]),
            "rate": float(conversion["rate"]),
            "currency_from": "USDC",
            "currency_to": "BIF",
            "ref": conversion["ref"],
        }
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/usdc/withdraw")
async def withdraw_usdc(
    payload: WithdrawUsdcRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        user_id = str(current_user.user_id)
        await ensure_usdc_wallet_account(user_id, db=db)
        withdrawal_id = await request_usdc_withdrawal(
            db,
            user_id=user_id,
            amount=payload.amount,
            to_address=payload.to_address,
            ref=f"WALLET_USDC_WITHDRAW:{user_id}:{payload.amount.normalize()}:{payload.to_address.strip()}",
        )
        await db.commit()
        return {
            "status": "PENDING",
            "withdrawal_id": withdrawal_id,
            "currency": "USDC",
        }
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

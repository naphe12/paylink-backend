from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.core.database import get_db
from schemas.escrow_swap import SwapExecuteResponse
from services.swap_engine import InternalInventorySwapProvider
from services.escrow_swap_service import EscrowSwapService

router = APIRouter(prefix="/escrow", tags=["Escrow - Swap"])

@router.post("/orders/{order_id}/swap", response_model=SwapExecuteResponse)
async def execute_swap(order_id: str, db: AsyncSession = Depends(get_db)):
    try:
        provider = InternalInventorySwapProvider(rate_usdc_usdt=Decimal("1.0"), fee_pct=Decimal("0.002"))
        svc = EscrowSwapService(provider=provider)
        swap = await svc.execute_swap(db, order_id)

        return SwapExecuteResponse(
            order_id=swap.order_id,
            status="SWAPPED",
            input_amount_usdc=swap.input_amount,
            output_amount_usdt=swap.output_amount,
            fee_amount_usdt=swap.fee_amount,
            executed_at=swap.executed_at,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

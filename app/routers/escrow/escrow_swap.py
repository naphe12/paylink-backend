from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from sqlalchemy import select

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.escrow_order import EscrowOrder
from app.models.users import Users
from app.services.audit_service import audit_log
from schemas.escrow_swap import SwapExecuteResponse
from services.swap_engine import InternalInventorySwapProvider
from services.escrow_swap_service import EscrowSwapService

router = APIRouter(prefix="/escrow", tags=["Escrow - Swap"])

@router.post("/orders/{order_id}/swap", response_model=SwapExecuteResponse)
async def execute_swap(
    order_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Users = Depends(get_current_user_db),
):
    try:
        before_order = await db.scalar(select(EscrowOrder).where(EscrowOrder.id == order_id))
        before = (
            {"status": str(before_order.status), "usdc_received": str(before_order.usdc_received)}
            if before_order
            else None
        )
        provider = InternalInventorySwapProvider(rate_usdc_usdt=Decimal("1.0"), fee_pct=Decimal("0.002"))
        svc = EscrowSwapService(provider=provider)
        swap = await svc.execute_swap(db, order_id)
        after_order = await db.scalar(select(EscrowOrder).where(EscrowOrder.id == order_id))
        after = (
            {
                "status": str(after_order.status),
                "usdt_received": str(after_order.usdt_received),
                "fee": str(after_order.conversion_fee_usdt),
            }
            if after_order
            else None
        )
        actor_id = getattr(actor, "id", None) or getattr(actor, "user_id", None)
        actor_role = getattr(actor, "role", None)
        await audit_log(
            db,
            actor_user_id=str(actor_id) if actor_id else None,
            actor_role=str(actor_role) if actor_role else None,
            action="ESCROW_SWAP_EXECUTED",
            entity_type="escrow_order",
            entity_id=str(order_id),
            before_state=before,
            after_state=after,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()

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

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escrow_order import EscrowOrder
from app.models.escrow_enums import EscrowOrderStatus
from app.models.escrow_event import EscrowEvent
from app.services.liquidity_guard import LiquidityGuard
from app.services.payout_orchestrator import assign_agent_and_notify

from services.swap_engine import InternalInventorySwapProvider
from services.escrow_swap_service import EscrowSwapService

AUTO_SWAP_RISK_THRESHOLD = 30

async def run_post_funded_worker(db: AsyncSession):
    res = await db.execute(
        select(EscrowOrder)
        .where(EscrowOrder.status == EscrowOrderStatus.FUNDED)
        .order_by(EscrowOrder.created_at.asc())
        .limit(50)
    )
    orders = res.scalars().all()

    provider = InternalInventorySwapProvider(
        rate_usdc_usdt=Decimal("1.0"),
        fee_pct=Decimal("0.002"),
    )
    swap_svc = EscrowSwapService(provider)

    for order in orders:
        try:
            if order.risk_score >= AUTO_SWAP_RISK_THRESHOLD:
                order.flags = list(set(order.flags + ["MANUAL_REVIEW"]))
                db.add(EscrowEvent(
                    order_id=order.id,
                    event_type="MANUAL_REVIEW_REQUIRED",
                    payload={"risk_score": order.risk_score},
                ))
                await db.commit()
                continue

            # Liquidity guard: ensure treasury can deliver the simulated USDT output.
            swap_preview = await provider.swap_usdc_to_usdt(order.usdc_received or Decimal("0"))
            await LiquidityGuard.assert_balance(
                db,
                account_code="TREASURY_USDT",
                token="USDT",
                required_amount=swap_preview.output_amount_usdt,
            )

            await swap_svc.execute_swap(db, order.id)
            assign_res = await assign_agent_and_notify(str(order.id), Decimal(str(order.bif_target or 0)))

            db.add(EscrowEvent(
                order_id=order.id,
                event_type="AUTO_PAYOUT_PENDING",
                payload={"assignment_id": assign_res.get("assignment_id")},
            ))
            await db.commit()

        except Exception as e:
            order.flags = list(set(order.flags + ["AUTO_FLOW_FAILED"]))
            db.add(EscrowEvent(
                order_id=order.id,
                event_type="AUTO_FLOW_ERROR",
                payload={"error": str(e)},
            ))
            await db.commit()

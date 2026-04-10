from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.payment_request_service import run_global_due_payment_request_maintenance
from app.services.savings_service import run_global_due_savings_auto_contributions
from app.services.scheduled_transfer_service import run_global_due_scheduled_transfers


async def run_product_automation_cycle(db: AsyncSession, *, batch_limit: int = 100) -> dict:
    payment_requests = await run_global_due_payment_request_maintenance(db, limit=batch_limit)
    scheduled_transfers = await run_global_due_scheduled_transfers(db, limit=batch_limit)
    savings = await run_global_due_savings_auto_contributions(db, limit=batch_limit)
    return {
        "payment_requests": payment_requests,
        "scheduled_transfers": scheduled_transfers,
        "savings": savings,
    }

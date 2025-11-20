from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mobilemoney_requests import MobileMoneyRequests
from app.models.transactions import Transactions
from app.services.admin_notifications import push_admin_notification

MAX_ATTEMPTS = 5
RETRY_DELAYS = [1, 5, 15, 30, 60]  # minutes


async def schedule_retry(request: MobileMoneyRequests, db: AsyncSession, error: str | None = None):
    request.attempts += 1
    if error:
        request.last_error = error
    if request.attempts >= MAX_ATTEMPTS:
        request.status = "failed"
        request.next_retry_at = None
        if request.user_id:
            await push_admin_notification(
                "mobilemoney_failed",
                db=db,
                user_id=request.user_id,
                severity="error",
                title="Mobile money en echec",
                message=f"Requete {request.request_id} vers {request.phone} echouee apres {request.attempts} tentatives.",
                metadata={
                    "phone": request.phone,
                    "amount": float(request.amount or 0),
                    "provider": request.provider,
                    "direction": request.direction,
                    "last_error": request.last_error,
                },
            )
    else:
        delay_minutes = RETRY_DELAYS[min(request.attempts - 1, len(RETRY_DELAYS) - 1)]
        request.next_retry_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
        request.status = "pending"
    request.updated_at = datetime.utcnow()
    await db.commit()


async def process_mobilemoney_retries(db: AsyncSession, send_callback):
    now = datetime.utcnow()
    stmt = (
        select(MobileMoneyRequests)
        .where(
            MobileMoneyRequests.status == "pending",
            MobileMoneyRequests.next_retry_at <= now,
        )
        .limit(50)
    )
    result = await db.execute(stmt)
    requests = result.scalars().all()

    for req in requests:
        try:
            tx = None
            if req.tx_id:
                tx = await db.get(Transactions, req.tx_id)
            await send_callback(req, tx, db)
            req.status = "succeeded"
            req.next_retry_at = None
            req.updated_at = datetime.utcnow()
            await db.commit()
        except Exception as exc:
            await schedule_retry(req, db, str(exc))

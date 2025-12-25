from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets

router = APIRouter(prefix="/admin/payment-requests", tags=["Admin Payment Requests"])


@router.get("")
async def list_payment_requests(
    status: str | None = Query(None, description="pending|succeeded|cancelled"),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    allowed_status = {"pending", "succeeded", "cancelled"}
    if status and status not in allowed_status:
        raise HTTPException(status_code=400, detail="Statut invalide")

    requester = aliased(Users)
    recipient = aliased(Users)

    conditions = [
        Transactions.channel == "internal",
        Transactions.description.ilike("Demande de paiement%"),
    ]
    if status:
        conditions.append(Transactions.status == status)

    stmt = (
        select(
            Transactions.tx_id,
            Transactions.amount,
            Transactions.currency_code,
            Transactions.status,
            Transactions.created_at,
            Transactions.updated_at,
            requester.full_name,
            requester.email,
            requester.paytag,
            requester.username,
            recipient.full_name,
            recipient.email,
            recipient.paytag,
            recipient.username,
        )
        .join(requester, requester.user_id == Transactions.initiated_by, isouter=True)
        .join(Wallets, Wallets.wallet_id == Transactions.receiver_wallet, isouter=True)
        .join(recipient, recipient.user_id == Wallets.user_id, isouter=True)
        .where(*conditions)
        .order_by(Transactions.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    results = []
    for row in rows:
        (
            tx_id,
            amount,
            currency_code,
            tx_status,
            created_at,
            updated_at,
            req_name,
            req_email,
            req_paytag,
            req_username,
            rec_name,
            rec_email,
            rec_paytag,
            rec_username,
        ) = row
        results.append(
            {
                "request_id": str(tx_id),
                "amount": float(amount),
                "currency_code": currency_code,
                "status": tx_status,
                "created_at": created_at,
                "updated_at": updated_at,
                "requester": req_name or req_email or req_paytag or req_username,
                "requester_email": req_email,
                "requester_paytag": req_paytag,
                "requester_username": req_username,
                "recipient": rec_name or rec_email or rec_paytag or rec_username,
                "recipient_email": rec_email,
                "recipient_paytag": rec_paytag,
                "recipient_username": rec_username,
            }
        )
    return results

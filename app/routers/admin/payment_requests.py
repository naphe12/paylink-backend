import decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_, func
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets

router = APIRouter(prefix="/admin/payment-requests", tags=["Admin Payment Requests"])


class AdminPaymentRequestCreate(BaseModel):
    user_identifier: str
    amount: decimal.Decimal
    reason: str | None = None  # credit | credit_line | other


async def _find_user(db: AsyncSession, identifier: str) -> Users | None:
    ident = identifier.strip()
    normalized = ident.lower()
    paytag = normalized if normalized.startswith("@") else f"@{normalized}"
    return await db.scalar(
        select(Users).where(
            or_(
                func.lower(Users.email) == normalized,
                func.lower(Users.username) == normalized,
                func.lower(Users.paytag) == paytag,
                Users.phone_e164 == ident,
            )
        )
    )


@router.post("")
async def create_admin_payment_request(
    payload: AdminPaymentRequestCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    amount = decimal.Decimal(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide")

    user = await _find_user(db, payload.user_identifier)
    if not user:
        raise HTTPException(status_code=404, detail="Client introuvable")

    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet client introuvable")

    description = "Demande de paiement (admin)"
    reason = payload.reason
    if reason == "credit":
        description = "Demande remboursement credit"
    elif reason == "credit_line":
        description = "Demande remboursement ligne de credit"

    tx = Transactions(
        tx_id=None,  # auto gen
        initiated_by=admin.user_id,
        receiver_wallet=wallet.wallet_id,
        amount=amount,
        currency_code=wallet.currency_code,
        channel="internal",
        status="pending",
        description=description,
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return {"request_id": str(tx.tx_id), "status": tx.status}


@router.get("")
async def list_payment_requests(
    status: str | None = None,
    limit: int = 200,
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
        requester.role == "admin",
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

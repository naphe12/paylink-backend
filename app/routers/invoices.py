import base64
import json
from datetime import datetime, timedelta
from uuid import UUID

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.dependencies.auth import get_current_agent, get_current_user
from app.models.invoices import Invoices
from app.models.notifications import Notifications
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.agent_ops import compute_agent_commission
from app.services.wallet_history import log_wallet_movement
from app.models.wallet_transactions import WalletEntryDirectionEnum
router = APIRouter(prefix="/invoices", tags=["Invoices"])


class InvoiceCreate(BaseModel):
    amount: float = Field(gt=0)
    currency_code: str = "BIF"
    description: str | None = None
    due_date: datetime | None = None


@router.post("/qr")
async def create_invoice_qr(
    payload: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    invoice = Invoices(
        merchant_id=current_user.user_id,
        amount=payload.amount,
        currency_code=payload.currency_code,
        customer_user=current_user.user_id,
        due_date=payload.due_date or datetime.utcnow() + timedelta(days=1),
        metadata_={"description": payload.description},
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    qr_payload = {
        "invoice_id": str(invoice.invoice_id),
        "amount": float(invoice.amount),
        "currency": invoice.currency_code,
    }
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(json.dumps(qr_payload))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    def iter_qr():
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        yield from buf

    return StreamingResponse(iter_qr(), media_type="image/png")


class InvoiceValidatePayload(BaseModel):
    qr_payload: str


@router.post("/qr/scan")
async def scan_invoice_qr(
    payload: InvoiceValidatePayload,
    db: AsyncSession = Depends(get_db),
    agent: Users = Depends(get_current_agent),
):
    decoded = json.loads(payload.qr_payload)
    invoice_id = decoded.get("invoice_id")
    if not invoice_id:
        raise HTTPException(400, "QR invalide")

    invoice = await db.scalar(
        select(Invoices).where(Invoices.invoice_id == invoice_id)
    )
    if not invoice:
        raise HTTPException(404, "Facture introuvable")
    if invoice.status != "unpaid":
        raise HTTPException(400, "Facture déjà traitée")

    customer = await db.get(Users, invoice.customer_user)
    return {
        "invoice_id": str(invoice.invoice_id),
        "amount": float(invoice.amount),
        "currency": invoice.currency_code,
        "customer": {
            "name": customer.full_name if customer else None,
            "email": customer.email if customer else None,
        },
    }


@router.post("/qr/confirm")
async def confirm_invoice_qr(
    payload: InvoiceValidatePayload,
    db: AsyncSession = Depends(get_db),
    agent: Users = Depends(get_current_agent),
):
    decoded = json.loads(payload.qr_payload)
    invoice_id = decoded.get("invoice_id")
    if not invoice_id:
        raise HTTPException(400, "QR invalide")

    invoice = await db.scalar(
        select(Invoices).where(Invoices.invoice_id == invoice_id)
    )
    if not invoice:
        raise HTTPException(404, "Facture introuvable")
    if invoice.status != "unpaid":
        raise HTTPException(400, "Facture déjà traitée")

    customer = await db.get(Users, invoice.customer_user)
    if not customer:
        raise HTTPException(404, "Client introuvable")

    customer_wallet = await db.scalar(
        select(Wallets).where(Wallets.user_id == customer.user_id)
    )
    if not customer_wallet or customer_wallet.available < invoice.amount:
        raise HTTPException(400, "Solde insuffisant")

    agent_wallet = await db.scalar(
        select(Wallets).where(Wallets.user_id == agent.user_id)
    )
    if not agent_wallet:
        raise HTTPException(404, "Wallet agent introuvable")

    customer_wallet.available -= invoice.amount
    agent_wallet.available += invoice.amount
    await log_wallet_movement(
        db,
        wallet=customer_wallet,
        user_id=customer.user_id,
        amount=invoice.amount,
        direction=WalletEntryDirectionEnum.DEBIT,
        operation_type="invoice_payment",
        reference=str(invoice.invoice_id),
        description=f"Paiement facture {invoice.invoice_id}",
    )
    await log_wallet_movement(
        db,
        wallet=agent_wallet,
        user_id=agent.user_id,
        amount=invoice.amount,
        direction="credit",
        operation_type="invoice_payment_agent",
        reference=str(invoice.invoice_id),
        description=f"Encaissement facture {invoice.invoice_id}",
    )

    tx = Transactions(
        amount=invoice.amount,
        currency_code=invoice.currency_code,
        channel="mobile_money",
        status="succeeded",
        initiated_by=customer.user_id,
        description=f"Paiement QR facture {invoice.invoice_id}",
    )
    db.add(tx)

    invoice.status = "paid"
    invoice.updated_at = datetime.utcnow()

    notif = Notifications(
        user_id=customer.user_id,
        subject="Facture payée",
        message=f"Votre facture {invoice.invoice_id} a été payée via un agent.",
        channel="in_app",
    )
    db.add(notif)

    await db.commit()

    return {
        "message": "Paiement confirmé",
        "invoice_id": str(invoice.invoice_id),
        "amount": float(invoice.amount),
        "transaction_id": str(tx.tx_id),
    }

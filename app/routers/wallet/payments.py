import decimal
import uuid

# app/routers/wallet.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.tontine_logic import apply_contribution_effect
from app.utils.notify import send_notification
from app.websocket_manager import ws_push_room
from app.services.wallet_history import log_wallet_movement

router = APIRouter()

@router.post("/request")
async def create_payment_request(
    to_email: str,
    amount: decimal.Decimal,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide")

    receiver = await db.scalar(select(Users).where(Users.email == to_email))
    if not receiver:
        raise HTTPException(status_code=404, detail="Destinataire introuvable")

    tx = Transactions(
        transaction_id=uuid.uuid4(),
        user_id=current_user.user_id,
        type="payment_request",
        amount=amount,
        currency="EUR",
        status="pending",
        details={"from": current_user.email, "to": receiver.email}
    )

    db.add(tx)
    await db.commit()
    await send_notification(str(receiver.user_id), f"💰 Nouvelle demande de paiement de {current_user.email} ({amount}€)")

    return {"message": f"Demande de {amount}€ envoyée à {to_email} ✅"}

@router.post("/request/{request_id}/respond")
async def respond_payment_request(
    request_id: uuid.UUID,
    action: str,  # 'accept' ou 'decline'
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    tx = await db.scalar(
        select(Transactions).where(Transactions.transaction_id == request_id)
    )
    if not tx or tx.type != "payment_request":
        raise HTTPException(status_code=404, detail="Demande introuvable")

    if tx.details.get("to") != current_user.email:
        raise HTTPException(status_code=403, detail="Non autorisé à répondre à cette demande")

    if action == "accept":
        # débit + crédit
        sender = await db.scalar(select(Users).where(Users.email == tx.details["to"]))
        receiver = await db.scalar(select(Users).where(Users.email == tx.details["from"]))
        sender_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == sender.user_id))
        receiver_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == receiver.user_id))

        if sender_wallet.available < tx.amount:
            raise HTTPException(status_code=400, detail="Solde insuffisant")

        sender_wallet.available -= tx.amount
        receiver_wallet.available += tx.amount
        await log_wallet_movement(
            db,
            wallet=sender_wallet,
            user_id=sender.user_id,
            amount=tx.amount,
            direction="debit",
            operation_type="payment_request_send",
            reference=str(request_id),
            description=f"Paiement accepté vers {receiver.email}",
        )
        await log_wallet_movement(
            db,
            wallet=receiver_wallet,
            user_id=receiver.user_id,
            amount=tx.amount,
            direction="credit",
            operation_type="payment_request_receive",
            reference=str(request_id),
            description=f"Paiement reçu de {sender.email}",
        )

        tx.status = "accepted"
        db.add(Transactions(
            transaction_id=uuid.uuid4(),
            user_id=sender.user_id,
            type="transfer",
            amount=-tx.amount,
            currency="EUR",
            status="completed",
            details={"to": tx.details["from"]}
        ))
        db.add(Transactions(
            transaction_id=uuid.uuid4(),
            user_id=receiver.user_id,
            type="transfer",
            amount=tx.amount,
            currency="EUR",
            status="completed",
            details={"from": tx.details["to"]}
        ))

    elif action == "decline":
        tx.status = "declined"

    else:
        raise HTTPException(status_code=400, detail="Action invalide")

    await db.commit()
    return {"message": f"Demande {action}ée avec succès ✅"}

import httpx
# app/routers/payments.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter(prefix="/payments", tags=["Payments"])

LUMICASH_ENDPOINT = "https://api.lumicash.bi/payment"   # à confirmer
LUMICASH_MERCHANT_ID = "XXXX"
LUMICASH_API_KEY = "XXXX"

@router.post("/lumicash/send")
async def send_lumicash(
    phone: str,
    amount: float,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    payload = {
        "merchantId": LUMICASH_MERCHANT_ID,
        "apiKey": LUMICASH_API_KEY,
        "phone": phone,
        "amount": amount,
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(LUMICASH_ENDPOINT, json=payload)

    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Échec Lumicash")

    # ✅ Ici tu confirmes la transaction dans ta DB
    # update balance, insert transactions table...

    return {"status": "success", "message": "Paiement envoyé via Lumicash ✅"}

import hashlib
import hmac
import json
from datetime import datetime

# app/routers/payments.py
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.tontinecontributions import TontineContributions
from app.models.transactions import Transactions
from app.realtime.manager import ws_manager  # créé en F

payments = APIRouter(prefix="/payments", tags=["Payments"])

def verify_signature(payload: dict, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    computed = hmac.new(secret.encode(), json.dumps(payload, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)

@payments.post("/lumicash/callback")
async def lumicash_callback(
    body: dict,
    db: AsyncSession = Depends(get_db),
    x_lumi_signature: str | None = Header(default=None),
):
    # 1) Vérifier la signature (adapter SECRET)
    SECRET = "CHANGE_ME_LUMICASH_WEBHOOK_SECRET"
    if not verify_signature(body, x_lumi_signature, SECRET):
        raise HTTPException(401, "Signature invalide")

    external_ref = body.get("external_ref")
    status = body.get("status")  # "succeeded" | "failed"
    if not external_ref or status not in {"succeeded", "failed"}:
        raise HTTPException(400, "Payload invalide")

    # 2) Retrouver la transaction
    tx = await db.scalar(select(Transactions).where(Transactions.external_ref == external_ref))
    if not tx:
        raise HTTPException(404, "Transaction inconnue")

    tx.status = "succeeded" if status == "succeeded" else "failed"
    tx.updated_at = datetime.utcnow()

    # 3) Mettre à jour la contribution liée
    contrib = await db.scalar(select(TontineContributions).where(TontineContributions.tx_id == tx.tx_id))
    if contrib:
        contrib.status = "paid" if status == "succeeded" else "failed"
        contrib.paid_at = datetime.utcnow()

    await db.commit()

    # 4) Notifier en temps réel (F)
    if contrib:
        await ws_manager.broadcast_tontine_event(
            tontine_id=str(contrib.tontine_id),
            event_type="contribution_update",
            payload={
                "user_id": str(contrib.user_id),
                "amount": str(contrib.amount),
                "status": contrib.status,
                "tx_id": str(tx.tx_id),
            }
        )

    return {"ok": True}

@router.post("/mobilemoney/callback")
async def mobilemoney_callback(payload: dict, db: AsyncSession = Depends(get_db)):

    reference = payload.get("ref")
    status = payload.get("status")  # "SUCCESS" ou "FAILED"

    contrib = await db.scalar(select(TontineContributions).where(TontineContributions.contribution_id == reference))
    if not contrib:
        return {"message": "Contribution inconnue"}

    if status == "SUCCESS":
        contrib.status = "paid"
        contrib.paid_at = datetime.utcnow()

        # Credit pot / ou payer membre en rotation
        await apply_contribution_effect(contrib.tontine_id, contrib.user_id, contrib.amount, db)

        # ✅ Notification instantanée → étape F
        await ws_push_room(contrib.tontine_id, {
            "type": "contribution_update",
            "user_id": str(contrib.user_id),
            "amount": float(contrib.amount),
            "status": "paid"
        })

    else:
        contrib.status = "failed"

    await db.commit()
    return {"message": "OK"}



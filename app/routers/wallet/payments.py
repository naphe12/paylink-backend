import decimal
import uuid
import hashlib
import hmac
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.tontinecontributions import TontineContributions
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.tontine_logic import apply_contribution_effect
from app.services.wallet_history import log_wallet_movement
from app.utils.notify import send_notification
from app.websocket_manager import ws_push_room
from app.realtime.manager import ws_manager

router = APIRouter(prefix="/wallet", tags=["Wallet Payments"])


class PaymentRequestCreate(BaseModel):
    to: str | None = None  # email, username ou paytag
    to_email: str | None = None  # compat arriere
    amount: decimal.Decimal


async def _find_user_by_identifier(db: AsyncSession, identifier: str) -> Users | None:
    """
    Recherche un utilisateur par email, username ou paytag.
    """
    ident = identifier.strip()
    normalized = ident.lower()
    paytag = normalized if normalized.startswith("@") else f"@{normalized}"
    return await db.scalar(
        select(Users).where(
            or_(
                func.lower(Users.email) == normalized,
                func.lower(Users.username) == normalized,
                func.lower(Users.paytag) == paytag,
            )
        )
    )


@router.post("/request")
async def create_payment_request(
    payload: PaymentRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    to_identifier = payload.to or payload.to_email
    amount = decimal.Decimal(payload.amount)

    if not to_identifier:
        raise HTTPException(status_code=400, detail="Destinataire manquant (email/username/paytag).")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide.")

    receiver = await _find_user_by_identifier(db, to_identifier)
    if not receiver:
        raise HTTPException(status_code=404, detail="Destinataire introuvable.")
    if receiver.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Impossible de s'auto-adresser une demande.")

    receiver_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == receiver.user_id))
    if not receiver_wallet:
        raise HTTPException(status_code=404, detail="Wallet destinataire introuvable.")

    currency_code = receiver_wallet.currency_code or "EUR"

    tx = Transactions(
        tx_id=uuid.uuid4(),
        initiated_by=current_user.user_id,
        sender_wallet=None,
        receiver_wallet=receiver_wallet.wallet_id,
        amount=amount,
        currency_code=currency_code,
        channel="internal",
        status="pending",
        description=f"Demande de paiement vers {receiver.email or receiver.paytag or receiver.username}",
    )

    db.add(tx)
    await db.commit()
    await send_notification(
        str(receiver.user_id),
        f"Nouvelle demande de paiement de {current_user.email or current_user.paytag} ({amount})",
    )

    return {"message": f"Demande de {amount} envoyee a {to_identifier}."}


@router.post("/request/{request_id}/respond")
async def respond_payment_request(
    request_id: uuid.UUID,
    action: str,  # 'accept' ou 'decline'
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    tx = await db.scalar(select(Transactions).where(Transactions.tx_id == request_id))
    if not tx or tx.channel != "internal":
        raise HTTPException(status_code=404, detail="Demande introuvable.")

    receiver_wallet = None
    if tx.receiver_wallet:
        receiver_wallet = await db.scalar(select(Wallets).where(Wallets.wallet_id == tx.receiver_wallet))
    if not receiver_wallet or receiver_wallet.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Non autorise a repondre a cette demande.")

    requester = None
    if tx.initiated_by:
        requester = await db.scalar(select(Users).where(Users.user_id == tx.initiated_by))

    if action == "accept":
        payer_wallet = receiver_wallet
        if payer_wallet.available < tx.amount:
            raise HTTPException(status_code=400, detail="Solde insuffisant.")

        requester_wallet = None
        if requester:
            requester_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == requester.user_id))
        if not requester_wallet:
            raise HTTPException(status_code=404, detail="Wallet du demandeur introuvable.")

        payer_wallet.available -= tx.amount
        requester_wallet.available += tx.amount

        await log_wallet_movement(
            db,
            wallet=payer_wallet,
            user_id=current_user.user_id,
            amount=tx.amount,
            direction="debit",
            operation_type="payment_request_send",
            reference=str(request_id),
            description=f"Paiement accepte vers {requester.email if requester else 'demandeur inconnu'}",
        )
        await log_wallet_movement(
            db,
            wallet=requester_wallet,
            user_id=requester_wallet.user_id,
            amount=tx.amount,
            direction="credit",
            operation_type="payment_request_receive",
            reference=str(request_id),
            description=f"Paiement recu de {current_user.email or current_user.paytag}",
        )

        tx.status = "succeeded"
        tx.sender_wallet = payer_wallet.wallet_id
        tx.receiver_wallet = requester_wallet.wallet_id
        tx.updated_at = datetime.utcnow()

    elif action == "decline":
        tx.status = "cancelled"
        tx.updated_at = datetime.utcnow()

    else:
        raise HTTPException(status_code=400, detail="Action invalide.")

    await db.commit()

    if requester:
        await send_notification(
            str(requester.user_id),
            f"Demande de paiement {action}e par {current_user.email or current_user.paytag}",
        )

    return {"message": f"Demande {action}e avec succes."}


@router.get("/requests")
async def list_payment_requests(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable.")

    stmt = (
        select(
            Transactions.tx_id,
            Transactions.amount,
            Transactions.currency_code,
            Transactions.status,
            Transactions.created_at,
            Users.full_name,
            Users.email,
            Users.username,
            Users.paytag,
        )
        .join(Wallets, Wallets.wallet_id == Transactions.receiver_wallet)
        .join(Users, Users.user_id == Transactions.initiated_by, isouter=True)
        .where(
            Transactions.channel == "internal",
            Transactions.status == "pending",
            Wallets.user_id == current_user.user_id,
        )
        .order_by(Transactions.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    def requester_display(row):
        return row.paytag or row.username or row.email or "Utilisateur"

    return [
        {
            "request_id": str(r.tx_id),
            "amount": float(r.amount),
            "currency_code": r.currency_code,
            "status": r.status,
            "created_at": r.created_at,
            "from": requester_display(r),
            "from_email": r.email,
            "from_paytag": r.paytag,
            "from_username": r.username,
        }
        for r in rows
    ]


# --- Lumicash / payments ---
payments = APIRouter(prefix="/payments", tags=["Payments"])


@payments.post("/lumicash/send")
async def send_lumicash(
    phone: str,
    amount: float,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    LUMICASH_ENDPOINT = "https://api.lumicash.bi/payment"  # a confirmer
    LUMICASH_MERCHANT_ID = "XXXX"
    LUMICASH_API_KEY = "XXXX"

    payload = {
        "merchantId": LUMICASH_MERCHANT_ID,
        "apiKey": LUMICASH_API_KEY,
        "phone": phone,
        "amount": amount,
    }

    import httpx

    async with httpx.AsyncClient() as client:
        res = await client.post(LUMICASH_ENDPOINT, json=payload)

    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Echec Lumicash")

    return {"status": "success", "message": "Paiement envoye via Lumicash."}


def verify_signature(payload: dict, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    computed = hmac.new(
        secret.encode(), json.dumps(payload, separators=(",", ":")).encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


@payments.post("/lumicash/callback")
async def lumicash_callback(
    body: dict,
    db: AsyncSession = Depends(get_db),
    x_lumi_signature: str | None = Header(default=None),
):
    SECRET = "CHANGE_ME_LUMICASH_WEBHOOK_SECRET"
    if not verify_signature(body, x_lumi_signature, SECRET):
        raise HTTPException(401, "Signature invalide")

    external_ref = body.get("external_ref")
    status = body.get("status")  # "succeeded" | "failed"
    if not external_ref or status not in {"succeeded", "failed"}:
        raise HTTPException(400, "Payload invalide")

    tx = await db.scalar(select(Transactions).where(Transactions.external_ref == external_ref))
    if not tx:
        raise HTTPException(404, "Transaction inconnue")

    tx.status = "succeeded" if status == "succeeded" else "failed"
    tx.updated_at = datetime.utcnow()

    contrib = await db.scalar(select(TontineContributions).where(TontineContributions.tx_id == tx.tx_id))
    if contrib:
        contrib.status = "paid" if status == "succeeded" else "failed"
        contrib.paid_at = datetime.utcnow()

    await db.commit()

    if contrib:
        await ws_manager.broadcast_tontine_event(
            tontine_id=str(contrib.tontine_id),
            event_type="contribution_update",
            payload={
                "user_id": str(contrib.user_id),
                "amount": str(contrib.amount),
                "status": contrib.status,
                "tx_id": str(tx.tx_id),
            },
        )

    return {"ok": True}


@router.post("/mobilemoney/callback")
async def mobilemoney_callback(payload: dict, db: AsyncSession = Depends(get_db)):
    reference = payload.get("ref")
    status = payload.get("status")  # "SUCCESS" ou "FAILED"

    contrib = await db.scalar(
        select(TontineContributions).where(TontineContributions.contribution_id == reference)
    )
    if not contrib:
        return {"message": "Contribution inconnue"}

    if status == "SUCCESS":
        contrib.status = "paid"
        contrib.paid_at = datetime.utcnow()

        await apply_contribution_effect(contrib.tontine_id, contrib.user_id, contrib.amount, db)

        await ws_push_room(
            contrib.tontine_id,
            {
                "type": "contribution_update",
                "user_id": str(contrib.user_id),
                "amount": float(contrib.amount),
                "status": "paid",
            },
        )

    else:
        contrib.status = "failed"

    await db.commit()
    return {"message": "OK"}

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import (
    get_current_agent,
    get_current_user,  # ou une version spéciale pour les agents
)
from app.models.agent_transactions import AgentTransactions
from app.models.external_transfers import ExternalTransfers
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions
from app.models.wallets import Wallets
from app.services.mailer import send_email

router = APIRouter(prefix="/agent/external", tags=["Agent External Transfers"])


@router.patch("/{transfer_id}/status")
async def update_external_transfer_status(
    transfer_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    """
    ✅ Route Agent :
    Met à jour le statut d'un transfert externe :
    - status = 'success' ou 'failed'
    - envoie email client
    - met à jour la transaction liée
    """

    new_status = payload.get("status")
    if new_status not in ["success", "failed"]:
        raise HTTPException(status_code=400, detail="Statut invalide (success/failed uniquement)")

    # 🔹 Récupère le transfert
    result = await db.execute(select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id))
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert introuvable")

    # 🔹 Met à jour le statut
    transfer.status = new_status

    # 🔹 Met à jour la transaction associée
    result_txn = await db.execute(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    txn = result_txn.scalar_one_or_none()
    if txn:
        txn.status = new_status

    await db.commit()

    # 🔹 Prépare l’email
    subject = f"Transfert {new_status.upper()} - Référence {transfer.reference_code}"

    if new_status == "success":
        msg = f"""
        Bonjour {transfer.user.full_name},

        ✅ Votre transfert a été effectué avec succès !

        Détails :
        - Référence : {transfer.reference_code}
        - Bénéficiaire : {transfer.recipient_name}
        - Téléphone : {transfer.recipient_phone}
        - Montant envoyé : {transfer.amount} EUR
        - Partenaire : {transfer.partner_name}
        - Pays destination : {transfer.country_destination}

        Merci d'utiliser PayLink 🌍
        """
    else:
        msg = f"""
        Bonjour {transfer.user.full_name},

        ❌ Votre transfert n’a pas pu être traité pour le moment.
        Référence : {transfer.reference_code}
        Montant : {transfer.amount} EUR

        Un agent vous contactera pour plus d’informations.
        """

    await run_in_threadpool(
        send_email,
        transfer.user.email,
        subject,
        None,
        body_html=msg,
    )

    return {"detail": f"Transfert {new_status} et e-mail envoyé."}

@router.get("/pending")
async def get_pending_transfers(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    if current_user.role not in ["agent", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé")

    result = await db.execute(
        select(ExternalTransfers).where(ExternalTransfers.status == "pending")
    )
    transfers = result.scalars().all()
    return transfers


@router.get("/ready")
async def get_ready_transfers(
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    stmt = select(ExternalTransfers).where(ExternalTransfers.status == "approved")
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{transfer_id}/close")
async def close_external_transfer(
    transfer_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    transfer = await db.scalar(
        select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id)
    )
    if not transfer or transfer.status != "approved":
        raise HTTPException(status_code=404, detail="Transfert introuvable ou déjà clos.")

    wallet = await db.scalar(
        select(Wallets).where(
            Wallets.user_id == current_agent.user_id,
            Wallets.type == "agent",
        )
    )
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille agent introuvable.")

    amount_to_debit = Decimal(transfer.local_amount or transfer.amount or 0)
    if amount_to_debit <= Decimal("0"):
        raise HTTPException(status_code=400, detail="Montant invalide.")

    if wallet.available < amount_to_debit:
        raise HTTPException(
            status_code=400,
            detail="Solde agent insuffisant pour couvrir le transfert.",
        )

    wallet.available -= amount_to_debit
    transfer.status = "success"
    transfer.processed_at = datetime.utcnow()
    transfer.processed_by = current_agent.user_id

    txn = await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    if txn:
        txn.status = "succeeded"
        txn.updated_at = datetime.utcnow()

    wallet_tx = WalletTransactions(
        wallet_id=wallet.wallet_id,
        user_id=current_agent.user_id,
        operation_type="external_transfer_close",
        direction="debit",
        amount=amount_to_debit,
        currency_code=wallet.currency_code,
        balance_after=wallet.available,
        reference=str(transfer.transfer_id),
        description=f"Clôture transfert {transfer.reference_code or transfer.reference}",
    )
    db.add(wallet_tx)

    agent_tx = AgentTransactions(
        agent_user_id=current_agent.user_id,
        client_user_id=transfer.user_id,
        direction="external_transfer",
        tx_type="external_transfer",
        amount=amount_to_debit,
        commission=Decimal("0"),
        status="completed",
        related_tx=transfer.transfer_id,
    )
    db.add(agent_tx)

    await db.commit()
    return {
        "message": "Transfert clôturé",
        "balance": float(wallet.available),
    }

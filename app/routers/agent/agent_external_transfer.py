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
from app.models.agents import Agents
from app.schemas.external_transfers import ExternalBeneficiaryRead

router = APIRouter(prefix="/agent/external", tags=["Agent External Transfers"])

async def _require_agent(db: AsyncSession, user: Users) -> Agents:
    agent = await db.scalar(select(Agents).where(Agents.user_id == user.user_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Profil agent introuvable.")
    return agent


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
    - status = 'succeeded' ou 'failed' (accepte aussi 'success' comme alias et normalise vers 'succeeded')
    - envoie email client
    - met à jour la transaction liée
    """

    raw_status = (payload.get("status") or "").lower()
    if raw_status not in ["succeeded", "success", "failed"]:
        raise HTTPException(status_code=400, detail="Statut invalide (succeeded/failed uniquement)")
    new_status = "succeeded" if raw_status in ["succeeded", "success"] else "failed"

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

    if new_status == "succeeded":
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
        raise HTTPException(status_code=403, detail="Acces refuse")

    stmt = (
        select(ExternalTransfers, Users.full_name, Users.email)
        .join(Users, Users.user_id == ExternalTransfers.user_id, isouter=True)
        .where(ExternalTransfers.status == "pending")
    )
    rows = (await db.execute(stmt)).all()

    serialized = []
    for transfer, full_name, email in rows:
        serialized.append(
            {
                "transfer_id": str(transfer.transfer_id),
                "user_id": str(transfer.user_id),
                "partner_name": transfer.partner_name,
                "country_destination": transfer.country_destination,
                "recipient_name": transfer.recipient_name,
                "recipient_phone": transfer.recipient_phone,
                "amount": float(transfer.amount),
                "currency": transfer.currency,
                "rate": float(transfer.rate) if transfer.rate is not None else None,
                "local_amount": float(transfer.local_amount) if transfer.local_amount is not None else None,
                "credit_used": bool(transfer.credit_used),
                "status": transfer.status,
                "reference_code": transfer.reference_code,
                "metadata": transfer.metadata_,
                "created_at": transfer.created_at,
                "processed_by": str(transfer.processed_by) if transfer.processed_by else None,
                "processed_at": transfer.processed_at,
                "user_name": full_name,
                "user_email": email,
            }
        )
    return serialized


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
    agent_row = await _require_agent(db, current_agent)
    agent_id = agent_row.agent_id
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
    transfer.status = "completed"
    transfer.processed_at = datetime.utcnow()
    transfer.processed_by = current_agent.user_id

    txn = await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    if txn:
        txn.status = "completed"
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
        agent_id=agent_id,
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


@router.get("/users")
async def list_external_users(
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    """
    Liste des utilisateurs qui ont déjà fait un transfert externe.
    """
    stmt = (
        select(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
        )
        .join(ExternalTransfers, ExternalTransfers.user_id == Users.user_id)
        .distinct()
        .order_by(Users.full_name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": str(r.user_id),
            "full_name": r.full_name,
            "email": r.email,
            "phone": r.phone_e164,
        }
        for r in rows
    ]


@router.get("/beneficiaries", response_model=list[ExternalBeneficiaryRead])
async def list_external_beneficiaries_for_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    """
    Bénéficiaires utilisés par un utilisateur pour ses transferts externes.
    """
    stmt = (
        select(
            ExternalTransfers.recipient_name,
            ExternalTransfers.recipient_phone,
            ExternalTransfers.partner_name,
            ExternalTransfers.country_destination,
        )
        .where(ExternalTransfers.user_id == user_id)
        .distinct()
        .order_by(ExternalTransfers.recipient_name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "recipient_name": r.recipient_name,
            "recipient_phone": r.recipient_phone,
            "partner_name": r.partner_name,
            "country_destination": r.country_destination,
        }
        for r in rows
    ]

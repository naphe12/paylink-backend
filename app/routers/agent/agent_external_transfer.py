from datetime import datetime
from decimal import Decimal
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
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
from app.services.transaction_notifications import send_transaction_emails
from app.models.agents import Agents
from app.schemas.external_transfers import ExternalBeneficiaryRead

router = APIRouter(prefix="/agent/external", tags=["Agent External Transfers"])

async def _require_agent(db: AsyncSession, user: Users) -> Agents:
    agent = await db.scalar(select(Agents).where(Agents.user_id == user.user_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Profil agent introuvable.")
    return agent


def _jsonify_metadata(value):
    """
    Ensure metadata content is JSON serializable for JSONB column.
    """
    if isinstance(value, (Decimal, UUID, datetime, date)):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonify_metadata(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify_metadata(v) for v in value]
    return value


@router.patch("/{transfer_id}/status")
async def update_external_transfer_status(
    transfer_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Route Agent :
    Met a jour le statut d'un transfert externe :
    - status = 'succeeded' ou 'failed' (accepte aussi 'success' comme alias et normalise vers 'succeeded')
    - envoie email client
    - met a jour la transaction liee
    """

    raw_status = (payload.get("status") or "").lower()
    if raw_status not in ["succeeded", "success", "failed"]:
        raise HTTPException(status_code=400, detail="Statut invalide (succeeded/failed uniquement)")
    new_status = "succeeded" if raw_status in ["succeeded", "success"] else "failed"

    transfer = await db.scalar(select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id))
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert introuvable")

    user = await db.scalar(select(Users).where(Users.user_id == transfer.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur lie introuvable")

    transfer.status = new_status
    transfer.processed_by = current_user.user_id
    transfer.processed_at = datetime.utcnow()

    metadata_payload = payload.get("metadata") or payload.get("product_metadata")
    merged_metadata = (transfer.metadata_ or {}).copy()
    merged_metadata.update(
        {
            "status": new_status,
            "processed_by_agent": str(current_user.user_id),
        }
    )
    if metadata_payload and isinstance(metadata_payload, dict):
        merged_metadata.update(metadata_payload)
    transfer.metadata_ = _jsonify_metadata(merged_metadata)

    txn = await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    if txn:
        txn.status = new_status
        txn.updated_at = datetime.utcnow()

    await db.commit()

    subject = f"Transfert {new_status.upper()} - Reference {transfer.reference_code}"

    if new_status == "succeeded":
        msg = f"""
        Bonjour {user.full_name},

        Votre transfert a ete effectue avec succes.

        Details :
        - Reference : {transfer.reference_code}
        - Beneficiaire : {transfer.recipient_name}
        - Telephone : {transfer.recipient_phone}
        - Montant envoye : {transfer.amount} EUR
        - Partenaire : {transfer.partner_name}
        - Pays destination : {transfer.country_destination}

        Merci d'utiliser PayLink.
        """
    else:
        msg = f"""
        Bonjour {user.full_name},

        Votre transfert n'a pas pu etre traite pour le moment.
        Reference : {transfer.reference_code}
        Montant : {transfer.amount} EUR

        Un agent vous contactera pour plus d'informations.
        """

    await send_transaction_emails(
        db,
        initiator=user,
        subject=subject,
        template=None,
        body=msg,
    )

    return {"detail": f"Transfert {new_status} et e-mail envoye."}

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
    payload: dict | None = Body(None),
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    agent_row = await _require_agent(db, current_agent)
    agent_id = agent_row.agent_id
    transfer = await db.scalar(
        select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id)
    )
    if not transfer or transfer.status != "approved":
        raise HTTPException(status_code=404, detail="Transfert introuvable ou deja clos.")

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
        description=f"Cloture transfert {transfer.reference_code or transfer.transfer_id}",
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

    await db.flush()

    metadata_payload = (payload or {}).get("metadata") or (payload or {}).get("product_metadata")
    metadata = (transfer.metadata_ or {}).copy()
    metadata.update(
        {
            "operation": "external_transfer_close",
            "transfer_id": str(transfer.transfer_id),
            "transaction_id": str(txn.tx_id) if txn else None,
            "agent_wallet_id": str(wallet.wallet_id),
            "agent_user_id": str(current_agent.user_id),
            "wallet_transaction_id": str(wallet_tx.transaction_id),
            "agent_transaction_id": str(agent_tx.transaction_id),
            "amount_debited": str(amount_to_debit),
            "currency": wallet.currency_code,
            "reference_code": transfer.reference_code,
        }
    )
    if metadata_payload and isinstance(metadata_payload, dict):
        metadata.update(metadata_payload)
    transfer.metadata_ = _jsonify_metadata({k: v for k, v in metadata.items() if v is not None})

    await db.commit()

    user = await db.scalar(select(Users).where(Users.user_id == transfer.user_id))
    if user:
        body = f"""
        Bonjour {user.full_name},

        Votre transfert {transfer.reference_code} a ete complete par un agent.
        Montant envoye : {transfer.amount} {transfer.currency}
        Beneficiaire : {transfer.recipient_name} ({transfer.recipient_phone})

        Merci d'utiliser PayLink.
        """
        await send_transaction_emails(
            db,
            initiator=user,
            subject=f"Transfert {transfer.reference_code} complete",
            template=None,
            body=body,
        )
    return {
        "message": "Transfert cloture",
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

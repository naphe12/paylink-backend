from datetime import datetime
from decimal import Decimal
from datetime import date
import re
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.dependencies.auth import (
    get_current_agent,
    get_current_user,  # ou une version spéciale pour les agents
)
from app.models.agent_transactions import AgentTransactions
from app.models.external_beneficiaries import ExternalBeneficiaries
from app.models.external_transfers import ExternalTransfers
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions
from app.models.wallets import Wallets
from app.services.transaction_notifications import send_transaction_emails
from app.models.agents import Agents
from app.schemas.external_transfers import ExternalBeneficiaryRead, ExternalTransferCreate
from app.routers.wallet.transfer import _external_transfer_core as create_client_external_transfer
from app.services.external_transfer_rules import (
    map_external_transfer_to_transaction_status,
    normalize_external_transfer_status,
    transition_external_transfer_status,
)

router = APIRouter(prefix="/agent/external", tags=["Agent External Transfers"])
EXTERNAL_TRANSFER_PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")


class AgentExternalTransferCreate(BaseModel):
    user_id: str
    partner_name: str
    country_destination: str
    recipient_name: str
    recipient_phone: str
    amount: Decimal

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


def _is_valid_external_phone(value: str | None) -> bool:
    return bool(EXTERNAL_TRANSFER_PHONE_RE.fullmatch(str(value or "").strip()))


def _extract_transfer_risk_flags(metadata: dict | None) -> dict:
    payload = dict(metadata or {})
    return {
        "review_reasons": list(payload.get("review_reasons") or []),
        "aml_reason_codes": list(payload.get("aml_reason_codes") or []),
        "aml_risk_score": payload.get("aml_risk_score"),
        "aml_manual_review_required": bool(payload.get("aml_manual_review_required")),
        "funding_pending": bool(payload.get("funding_pending")),
        "required_credit_topup": payload.get("required_credit_topup"),
    }


def _transfer_origin_currency(transfer: ExternalTransfers, fallback: str = "EUR") -> str:
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    return str(metadata.get("origin_currency") or fallback or "EUR").upper()


def _transfer_destination_currency(transfer: ExternalTransfers, fallback: str = "BIF") -> str:
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    return str(metadata.get("destination_currency") or transfer.currency or fallback or "BIF").upper()


async def _ensure_transfer_transaction(
    db: AsyncSession,
    transfer: ExternalTransfers,
    fallback_tx: Transactions | None,
) -> Transactions:
    """
    Garantit qu'une ligne Transactions existe avec tx_id == transfer.transfer_id
    (FK strict coté DB). Si absente, on en crée une minimale en copiant les
    infos connues du tx lié (related_entity_id) si disponible.
    """
    tx_by_id = await db.scalar(select(Transactions).where(Transactions.tx_id == transfer.transfer_id))
    if tx_by_id:
        return tx_by_id

    amount = fallback_tx.amount if fallback_tx else transfer.amount or Decimal("0")
    currency_code = fallback_tx.currency_code if fallback_tx else _transfer_origin_currency(transfer)
    new_tx = Transactions(
        tx_id=transfer.transfer_id,  # respecte le FK
        amount=amount,
        currency_code=currency_code,
        channel="external_transfer",
        status=fallback_tx.status if fallback_tx else map_external_transfer_to_transaction_status(transfer.status),
        initiated_by=fallback_tx.initiated_by if fallback_tx else transfer.user_id,
        sender_wallet=fallback_tx.sender_wallet if fallback_tx else None,
        receiver_wallet=fallback_tx.receiver_wallet if fallback_tx else None,
        related_entity_id=transfer.transfer_id,
        description=fallback_tx.description if fallback_tx else f"External transfer {transfer.reference_code}",
    )
    db.add(new_tx)
    await db.flush()
    return new_tx


async def _close_external_transfer_core(
    db: AsyncSession,
    transfer_id: str,
    acting_agent_user: Users,
    payload: dict | None = None,
):
    agent_row = await _require_agent(db, acting_agent_user)
    agent_id = agent_row.agent_id
    transfer = await db.scalar(
        select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id)
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert introuvable ou deja clos.")
    current_status = normalize_external_transfer_status(transfer.status)
    if current_status in {"completed", "succeeded", "partially_repaid", "repaid"}:
        wallet = await db.scalar(
            select(Wallets).where(
                Wallets.user_id == acting_agent_user.user_id,
                Wallets.type == "agent",
            )
        )
        return {
            "message": "Transfert deja cloture",
            "balance": float(wallet.available) if wallet else None,
            "amount_debited": None,
            "currency": wallet.currency_code if wallet else None,
        }
    if current_status != "approved":
        raise HTTPException(status_code=400, detail=f"Transfert non cloturable (status={transfer.status})")

    wallet = await db.scalar(
        select(Wallets).where(
            Wallets.user_id == acting_agent_user.user_id,
            Wallets.type == "agent",
        )
    )
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille agent introuvable.")

    wallet_ccy = str(wallet.currency_code or "").upper()
    transfer_ccy = _transfer_destination_currency(transfer)
    if wallet_ccy == transfer_ccy and transfer.local_amount is not None:
        amount_to_debit = Decimal(transfer.local_amount)
    else:
        amount_to_debit = Decimal(transfer.amount or 0)

    if amount_to_debit <= Decimal("0"):
        raise HTTPException(status_code=400, detail="Montant invalide.")

    if wallet.available < amount_to_debit:
        raise HTTPException(
            status_code=400,
            detail="Solde agent insuffisant pour couvrir le transfert.",
        )

    wallet.available -= amount_to_debit
    transition_external_transfer_status(transfer, "completed")
    transfer.processed_at = datetime.utcnow()
    transfer.processed_by = acting_agent_user.user_id

    txn = await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    txn = await _ensure_transfer_transaction(db, transfer, txn)
    txn.status = map_external_transfer_to_transaction_status(transfer.status)
    txn.updated_at = datetime.utcnow()

    wallet_tx = WalletTransactions(
        wallet_id=wallet.wallet_id,
        user_id=acting_agent_user.user_id,
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
            "agent_user_id": str(acting_agent_user.user_id),
            "wallet_transaction_id": str(wallet_tx.transaction_id),
            "agent_transaction_id": str(agent_tx.transaction_id),
            "amount_debited": str(amount_to_debit),
            "currency": wallet.currency_code,
            "reference_code": transfer.reference_code,
            "closed_via": "agent_link" if (payload or {}).get("_source") == "agent_link" else "agent_console",
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
        Montant envoye : {transfer.amount} {_transfer_origin_currency(transfer)}
        Beneficiaire : {transfer.recipient_name} ({transfer.recipient_phone})

        Merci d'utiliser paylink.
        """
        await send_transaction_emails(
            db,
            initiator=user,
            subject=f"Transfert {transfer.reference_code} complete",
            template=None,
            body=body,
            recipients=[user.email],
        )

    return {
        "message": "Transfert cloture",
        "balance": float(wallet.available),
        "amount_debited": float(amount_to_debit),
        "currency": wallet.currency_code,
    }


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

    raw_status = normalize_external_transfer_status(payload.get("status"))
    if raw_status not in ["succeeded", "failed"]:
        raise HTTPException(status_code=400, detail="Statut invalide (succeeded/failed uniquement)")
    new_status = raw_status

    transfer = await db.scalar(select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id))
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert introuvable")

    user = await db.scalar(select(Users).where(Users.user_id == transfer.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur lie introuvable")

    try:
        transition_external_transfer_status(transfer, new_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    txn = await _ensure_transfer_transaction(db, transfer, txn)
    txn.status = map_external_transfer_to_transaction_status(transfer.status)
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

        Merci d'utiliser paylink.
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
        recipients=[user.email],
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
        metadata = dict(transfer.metadata_ or {})
        serialized.append(
            {
                "transfer_id": str(transfer.transfer_id),
                "user_id": str(transfer.user_id),
                "partner_name": transfer.partner_name,
                "country_destination": transfer.country_destination,
                "recipient_name": transfer.recipient_name,
                "recipient_phone": transfer.recipient_phone,
                "amount": float(transfer.amount),
                "currency": _transfer_origin_currency(transfer),
                "rate": float(transfer.rate) if transfer.rate is not None else None,
                "local_amount": float(transfer.local_amount) if transfer.local_amount is not None else None,
                "local_currency": _transfer_destination_currency(transfer),
                "credit_used": bool(transfer.credit_used),
                "status": transfer.status,
                "reference_code": transfer.reference_code,
                "metadata": metadata,
                "created_at": transfer.created_at,
                "processed_by": str(transfer.processed_by) if transfer.processed_by else None,
                "processed_at": transfer.processed_at,
                "user_name": full_name,
                "user_email": email,
                **_extract_transfer_risk_flags(metadata),
            }
        )
    return serialized


@router.post("/create")
async def create_external_transfer_for_client(
    payload: AgentExternalTransferCreate,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    client_user = await db.scalar(select(Users).where(Users.user_id == payload.user_id))
    if not client_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    if str(client_user.role or "").lower() not in {"client", "user"}:
        raise HTTPException(status_code=400, detail="Selectionnez un client valide.")

    transfer_payload = ExternalTransferCreate(
        partner_name=payload.partner_name,
        country_destination=payload.country_destination,
        recipient_name=payload.recipient_name,
        recipient_phone=payload.recipient_phone,
        amount=payload.amount,
    )

    result = await create_client_external_transfer(
        data=transfer_payload,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        current_user=client_user,
        override_balance_check=str(getattr(current_agent, "paytag", "") or "").strip().lower() == "@agent_adolphe",
        override_context={
            "agent_user_id": str(current_agent.user_id),
            "agent_paytag": getattr(current_agent, "paytag", None),
            "source": "agent_console",
            "notify_agent_email": getattr(current_agent, "email", None),
            "notify_agent_name": getattr(current_agent, "full_name", None),
        },
        final_status_override="approved",
    )

    transfer_id = getattr(result, "transfer_id", None) or result.get("transfer_id")
    if transfer_id:
        transfer = await db.scalar(select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id))
        if transfer:
            metadata = (transfer.metadata_ or {}).copy()
            metadata.update(
                {
                    "created_via": "agent_console",
                    "created_by_agent_user_id": str(current_agent.user_id),
                    "auto_approved_by_agent": True,
                }
            )
            transfer.metadata_ = _jsonify_metadata(metadata)
            await db.commit()

    return result


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
    return await _close_external_transfer_core(
        db=db,
        transfer_id=transfer_id,
        acting_agent_user=current_agent,
        payload=payload,
    )


@router.get("/{transfer_id}/close-by-link")
async def close_external_transfer_by_link(
    transfer_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_access_token(token)
    if payload.get("action") != "external_transfer_close_by_agent_link":
        raise HTTPException(status_code=403, detail="Token invalide pour cette action")

    if str(payload.get("transfer_id") or "") != str(transfer_id):
        raise HTTPException(status_code=403, detail="Token transfer mismatch")

    agent_user_id = str(payload.get("sub") or "").strip()
    if not agent_user_id:
        raise HTTPException(status_code=403, detail="Token agent invalide")

    acting_agent_user = await db.scalar(select(Users).where(Users.user_id == agent_user_id))
    if not acting_agent_user:
        raise HTTPException(status_code=404, detail="Agent introuvable")

    return await _close_external_transfer_core(
        db=db,
        transfer_id=transfer_id,
        acting_agent_user=acting_agent_user,
        payload={"_source": "agent_link"},
    )


@router.get("/users")
async def list_external_users(
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    """
    Liste tous les clients utilisables pour un transfert externe agent.
    """
    last_external_transfer_at_sq = (
        select(func.max(ExternalTransfers.created_at))
        .where(ExternalTransfers.user_id == Users.user_id)
        .correlate(Users)
        .scalar_subquery()
    )
    last_wallet_activity_at_sq = (
        select(func.max(WalletTransactions.created_at))
        .where(WalletTransactions.user_id == Users.user_id)
        .correlate(Users)
        .scalar_subquery()
    )
    last_agent_activity_at_sq = (
        select(func.max(AgentTransactions.created_at))
        .where(AgentTransactions.client_user_id == Users.user_id)
        .correlate(Users)
        .scalar_subquery()
    )
    recent_activity_at = func.greatest(
        func.coalesce(last_external_transfer_at_sq, Users.created_at),
        func.coalesce(last_wallet_activity_at_sq, Users.created_at),
        func.coalesce(last_agent_activity_at_sq, Users.created_at),
        Users.created_at,
    )
    recent_activity_type = case(
        (
            func.coalesce(last_external_transfer_at_sq, Users.created_at)
            >= func.coalesce(last_wallet_activity_at_sq, Users.created_at),
            case(
                (
                    func.coalesce(last_external_transfer_at_sq, Users.created_at)
                    >= func.coalesce(last_agent_activity_at_sq, Users.created_at),
                    "transfer",
                ),
                else_="agent_operation",
            ),
        ),
        else_=case(
            (
                func.coalesce(last_wallet_activity_at_sq, Users.created_at)
                >= func.coalesce(last_agent_activity_at_sq, Users.created_at),
                "wallet_operation",
            ),
            else_="agent_operation",
        ),
    )
    wallet_currency_sq = (
        select(Wallets.currency_code)
        .where(
            Wallets.user_id == Users.user_id,
            Wallets.type.in_(["consumer", "personal"]),
        )
        .order_by(Wallets.wallet_id.desc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
            wallet_currency_sq.label("wallet_currency"),
            recent_activity_at.label("recent_activity_at"),
            recent_activity_type.label("recent_activity_type"),
        )
        .where(Users.role.in_(["client", "user"]))
        .order_by(recent_activity_at.desc(), Users.full_name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": str(r.user_id),
            "full_name": r.full_name,
            "email": r.email,
            "phone": r.phone_e164,
            "currency": str(r.wallet_currency or "EUR").upper(),
            "recent_activity_at": r.recent_activity_at,
            "recent_activity_type": r.recent_activity_type,
        }
        for r in rows
    ]


@router.get("/beneficiaries")
async def list_external_beneficiaries_for_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    """
    Bénéficiaires utilisés par un utilisateur pour ses transferts externes.
    """
    stmt = (
        select(ExternalTransfers)
        .where(ExternalTransfers.user_id == user_id)
        .order_by(ExternalTransfers.created_at.desc())
    )
    saved_stmt = (
        select(ExternalBeneficiaries)
        .where(
            ExternalBeneficiaries.user_id == user_id,
            ExternalBeneficiaries.is_active.is_(True),
        )
        .order_by(ExternalBeneficiaries.recipient_name.asc())
    )
    transfers = (await db.execute(stmt)).scalars().all()
    saved = (await db.execute(saved_stmt)).scalars().all()
    beneficiaries: dict[tuple[str, str, str], dict] = {}

    for row in saved:
        phone = str(row.recipient_phone or "").strip()
        if not _is_valid_external_phone(phone):
            continue
        account_ref = str(row.recipient_email or "").strip().lower()
        beneficiaries[(str(row.partner_name or "").strip().lower(), phone, account_ref)] = {
            "recipient_name": row.recipient_name,
            "recipient_phone": phone or None,
            "account_ref": account_ref or None,
            "recipient_email": str(row.recipient_email or "").strip().lower() or None,
            "partner_name": row.partner_name,
            "country_destination": row.country_destination,
            "source": "saved_beneficiary",
        }

    for row in transfers:
        phone = str(row.recipient_phone or "").strip()
        if not _is_valid_external_phone(phone):
            continue
        metadata = dict(row.metadata_ or {})
        account_ref = str(metadata.get("recipient_email") or "").strip().lower()
        key = (str(row.partner_name or "").strip().lower(), phone, account_ref)
        beneficiaries.setdefault(
            key,
            {
                "recipient_name": row.recipient_name,
                "recipient_phone": phone or None,
                "account_ref": account_ref or None,
                "recipient_email": str(metadata.get("recipient_email") or "").strip().lower() or None,
                "partner_name": row.partner_name,
                "country_destination": row.country_destination,
                "source": "transfer_history",
            },
        )

    return sorted(
        beneficiaries.values(),
        key=lambda item: (str(item.get("recipient_name") or "").lower(), str(item.get("partner_name") or "").lower()),
    )

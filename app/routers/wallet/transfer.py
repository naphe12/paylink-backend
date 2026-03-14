import decimal
import logging
import uuid
from datetime import datetime
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_agent, get_current_user
from app.models.bonus_history import BonusHistory
from app.models.credit_line_history import CreditLineHistory
from app.models.external_transfers import ExternalTransfers
from app.models.telegram_user import TelegramUser
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_transactions import WalletEntryDirectionEnum
from app.models.wallets import Wallets
from app.schemas.external_transfers import (
    ExternalBeneficiaryRead,
    ExternalTransferCreate,
    ExternalTransferRead,
)
from app.schemas.transactions import TransactionSend
from app.services.aml import update_risk_score
from app.services.ledger import LedgerLine, LedgerService
from app.services.mailer import send_email
from app.services.risk_engine import calculate_risk_score
from app.services.mailjet_service import MailjetEmailService
from app.services.telegram import send_message as send_telegram_message
from app.services.transaction_notifications import send_transaction_emails
from app.services.wallet_history import log_wallet_movement
from app.services.pdf_utils import build_external_transfer_receipt
from app.services.idempotency_service import (
    acquire_idempotency,
    compute_request_hash,
    store_idempotency_response,
)
from app.models.general_settings import GeneralSettings
from app.models.fx_custom_rates import FxCustomRates
from app.models.fxconversions import FxConversions
from app.core.security import create_access_token
from app.services.external_transfer_rules import transition_external_transfer_status

router = APIRouter(prefix="/wallet/transfer", tags=["External Transfer"])
logger = logging.getLogger(__name__)

DESTINATION_CURRENCY_MAP = {
    "burundi": "BIF",
    "rwanda": "RWF",
    "drc": "CDF",
    "rd congo": "CDF",
    "democratic republic of congo": "CDF",
    "rdc": "CDF",
}


def _get_destination_currency(country: str) -> str:
    """
    Map country names to currency codes; fall back to the provided value or EUR.
    """
    key = (country or "").strip().lower()
    return DESTINATION_CURRENCY_MAP.get(key, country or "EUR")


async def _resolve_fx_rate(
    db: AsyncSession,
    origin: str,
    destination: str,
) -> decimal.Decimal:
    """
    Choisit un taux :
    - si paire contient le BIF, on prend FxCustomRates (actif, le plus récent)
    - sinon on prend le dernier FxConversions
    - fallback sur 1.0
    """
    if origin == destination:
        return decimal.Decimal("1")

    if origin == "BIF" or destination == "BIF":
        custom = await db.scalar(
            select(FxCustomRates)
            .where(
                FxCustomRates.origin_currency == origin,
                FxCustomRates.destination_currency == destination,
                FxCustomRates.is_active.is_(True),
            )
            .order_by(FxCustomRates.updated_at.desc())
        )
        if custom and custom.rate:
            return decimal.Decimal(custom.rate)

    fx_row = await db.scalar(
        select(FxConversions.rate_used)
        .where(
            FxConversions.from_currency == origin,
            FxConversions.to_currency == destination,
        )
        .order_by(FxConversions.created_at.desc())
        .limit(1)
    )
    if fx_row:
        return decimal.Decimal(fx_row)
    return decimal.Decimal("1")


def _parse_telegram_notify_chat_ids() -> list[int]:
    raw = str(getattr(settings, "TELEGRAM_NOTIFY_CHAT_IDS", "") or "").strip()
    if not raw:
        return []
    chat_ids: list[int] = []
    for chunk in raw.split(","):
        candidate = chunk.strip()
        if not candidate:
            continue
        try:
            chat_ids.append(int(candidate))
        except Exception:
            continue
    return chat_ids


async def _notify_external_transfer(
    *,
    db: AsyncSession,
    current_user: Users,
    transfer: ExternalTransfers,
    data: ExternalTransferCreate,
    amount: decimal.Decimal,
    origin_currency: str,
    destination_currency: str,
    local_amount: decimal.Decimal,
    credit_used: decimal.Decimal,
    credit_available_after: decimal.Decimal,
    requires_admin: bool,
    fx_rate: decimal.Decimal,
) -> None:
    close_link = None
    configured_agent_email = str(getattr(settings, "AGENT_EMAIL", "") or "").strip()
    agent_user = await db.scalar(
        select(Users).where(Users.email == configured_agent_email)
    ) if configured_agent_email else None
    backend_base = str(getattr(settings, "BACKEND_URL", "") or "").strip()
    if agent_user and backend_base:
        close_token = create_access_token(
            data={
                "sub": str(agent_user.user_id),
                "action": "external_transfer_close_by_agent_link",
                "transfer_id": str(transfer.transfer_id),
            },
            expires_delta=timedelta(hours=48),
        )
        close_link = f"{backend_base.rstrip('/')}/agent/external/{transfer.transfer_id}/close-by-link?token={close_token}"

    if requires_admin and configured_agent_email:
        try:
            await run_in_threadpool(
                send_email,
                configured_agent_email,
                f"Nouvelle demande de transfert #{transfer.reference_code}",
                "external_transfer_request_agent.html",
                client_name=current_user.full_name,
                client_email=current_user.email,
                client_phone=current_user.phone_e164 or "",
                amount=amount,
                currency=origin_currency,
                payout_amount=f"{local_amount} {destination_currency}",
                used_credit=f"{credit_used} {origin_currency}",
                receiver_name=data.recipient_name,
                receiver_phone=data.recipient_phone,
                partner_name=data.partner_name,
                country=data.country_destination,
                transfer_id=transfer.reference_code,
                dashboard_url=f"{settings.FRONTEND_URL}/dashboard/admin",
                close_link=close_link,
                year=datetime.utcnow().year,
            )
        except Exception as exc:
            logger.exception(
                "Agent notification email failed for external transfer %s: %s",
                transfer.transfer_id,
                exc,
            )

    configured_chat_ids = _parse_telegram_notify_chat_ids()
    if configured_chat_ids:
        chat_ids = configured_chat_ids
    else:
        chat_ids = (await db.execute(select(TelegramUser.chat_id))).scalars().all()
    telegram_message = (
        "Nouveau transfert externe\n"
        f"Client: {current_user.full_name}\n"
        f"Montant: {amount} {origin_currency}\n"
        f"Pays: {data.country_destination}\n"
        f"Partenaire: {data.partner_name}\n"
        f"Reference: {transfer.reference_code}\n"
        f"Statut: {transfer.status}"
    )
    for chat_id in chat_ids:
        try:
            await send_telegram_message(int(chat_id), telegram_message)
        except Exception as exc:
            logger.exception(
                "Telegram notification failed for transfer %s to chat_id=%s: %s",
                transfer.transfer_id,
                chat_id,
                exc,
            )

    try:
        await send_transaction_emails(
            db,
            initiator=current_user,
            subject=f"Nouvelle demande de transfert {transfer.reference_code}",
            template="external_transfer_request_agent.html",
            client_name=current_user.full_name,
            client_email=current_user.email,
            client_phone=current_user.phone_e164 or "",
            amount=amount,
            currency=origin_currency,
            payout_amount=f"{local_amount} {destination_currency}",
            credit_available=f"{credit_available_after}",
            receiver_name=data.recipient_name,
            receiver_phone=data.recipient_phone,
            partner_name=data.partner_name,
            country=data.country_destination,
            transfer_id=transfer.reference_code,
            dashboard_url=f"{settings.FRONTEND_URL}/dashboard/admin",
            close_link=close_link,
            year=datetime.utcnow().year,
        )
    except Exception as exc:
        logger.exception(
            "Transaction notifications failed for external transfer %s: %s",
            transfer.transfer_id,
            exc,
        )

    if current_user.email:
        receipt_payload = {
            "reference_code": transfer.reference_code,
            "sender_name": current_user.full_name or "",
            "sender_email": current_user.email or "",
            "sender_phone": current_user.phone_e164 or "",
            "recipient_name": data.recipient_name,
            "recipient_phone": data.recipient_phone,
            "amount": amount,
            "currency": origin_currency,
            "local_amount": local_amount,
            "local_currency": destination_currency,
            "rate": fx_rate,
            "created_at": transfer.created_at,
            "status": transfer.status,
            "partner": data.partner_name,
            "country": data.country_destination,
        }
        receipt_bytes = build_external_transfer_receipt(receipt_payload)
        try:
            await send_transaction_emails(
                db,
                initiator=current_user,
                subject=f"Reçu PesaPaid {transfer.reference_code}",
                template="external_transfer_receipt.html",
                recipients=[current_user.email],
                client_name=current_user.full_name or "",
                reference=transfer.reference_code,
                amount=str(amount),
                currency=origin_currency,
                payout_amount=f"{local_amount} {destination_currency}",
                receiver_name=data.recipient_name,
                receiver_phone=data.recipient_phone,
                partner_name=data.partner_name,
                country=data.country_destination,
                status=transfer.status,
                year=datetime.utcnow().year,
                attachments=[
                    {"name": f"recu-{transfer.reference_code}.pdf", "content": receipt_bytes}
                ],
            )
        except Exception as exc:
            logger.exception(
                "Receipt email failed for external transfer %s: %s",
                transfer.transfer_id,
                exc,
            )


@router.get("/external/beneficiaries", response_model=list[ExternalBeneficiaryRead])
async def list_external_beneficiaries(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Liste des bénéficiaires déjà utilisés par l'utilisateur pour ses transferts externes.
    """
    stmt = (
        select(
            ExternalTransfers.recipient_name,
            ExternalTransfers.recipient_phone,
            ExternalTransfers.partner_name,
            ExternalTransfers.country_destination,
        )
        .where(ExternalTransfers.user_id == current_user.user_id)
        .distinct()
        .order_by(ExternalTransfers.recipient_name.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
          "recipient_name": r.recipient_name,
          "recipient_phone": r.recipient_phone,
          "partner_name": r.partner_name,
          "country_destination": r.country_destination,
        }
        for r in rows
    ]


@router.post("/external", response_model=ExternalTransferRead)
async def external_transfer(
    data: ExternalTransferCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    ledger = LedgerService(db)
    await calculate_risk_score(db, current_user.user_id)

    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "partner_name": str(data.partner_name or "").strip(),
                "country_destination": str(data.country_destination or "").strip(),
                "recipient_name": str(data.recipient_name or "").strip(),
                "recipient_phone": str(data.recipient_phone or "").strip(),
                "amount": str(data.amount),
                "user_id": str(current_user.user_id),
            }
        )
        scoped_idempotency_key = f"external_transfer:{current_user.user_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key deja utilisee avec un payload different.",
            )
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(
                status_code=409,
                detail="Requete dupliquee en cours de traitement. Reessayez dans quelques secondes.",
            )

    amount = decimal.Decimal(data.amount)
    if amount <= decimal.Decimal("0"):
        raise HTTPException(status_code=400, detail="Montant invalide")

    user_locked = await db.scalar(
        select(Users).where(Users.user_id == current_user.user_id).with_for_update()
    )
    if not user_locked:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user_locked.status == "frozen":
        raise HTTPException(423, "Votre compte est gele pour raisons de securite.")
    result = await db.execute(
        select(Wallets)
        .where(Wallets.user_id == current_user.user_id)
        .with_for_update()
    )
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    wallet_balance = decimal.Decimal(wallet.available or 0)
    credit_limit = decimal.Decimal(user_locked.credit_limit or 0)
    credit_used_total = decimal.Decimal(user_locked.credit_used or 0)
    credit_available = max(credit_limit - credit_used_total, decimal.Decimal(0))
    credit_available_before = credit_available
    settings_row = await db.scalar(
        select(GeneralSettings).order_by(GeneralSettings.created_at.desc())
    )
    fee_rate = decimal.Decimal(getattr(settings_row, "charge", 0) or 0)
    fee_amount = (amount * fee_rate / decimal.Decimal(100)).quantize(decimal.Decimal("0.01"))

    origin_currency = wallet.currency_code or "EUR"
    destination_currency = _get_destination_currency(data.country_destination)
    fx_rate = await _resolve_fx_rate(db, origin_currency, destination_currency)

    total_required = amount + fee_amount
    total_available = wallet_balance + credit_available

    if total_required > total_available:
        raise HTTPException(
            status_code=400,
            detail=f"Montant trop eleve. Disponible total : {total_available} {origin_currency}",
        )

    used_daily = decimal.Decimal(user_locked.used_daily or 0)
    used_monthly = decimal.Decimal(user_locked.used_monthly or 0)
    daily_limit = decimal.Decimal(user_locked.daily_limit or 0)
    monthly_limit = decimal.Decimal(user_locked.monthly_limit or 0)

    if daily_limit > 0 and amount + used_daily > daily_limit:
        raise HTTPException(400, "Limite journaliere atteinte. Passez au niveau KYC superieur.")

    if monthly_limit > 0 and amount + used_monthly > monthly_limit:
        raise HTTPException(400, "Limite mensuelle atteinte.")

    risk = await update_risk_score(db, current_user, amount, channel="external")
    if risk >= 80:
        raise HTTPException(423, "Transfert bloque : votre compte necessite une verification d'identite.")
    elif risk >= 60:
        raise HTTPException(423, "Niveau de risque eleve. Merci de completer votre KYC.")

    if current_user.external_transfers_blocked:
        raise HTTPException(423, "Transferts externes temporairement suspendus.")

    wallet_balance_before = wallet_balance
    credit_available_after = credit_available_before
    local_amount = (amount * fx_rate).quantize(decimal.Decimal("0.01"))
    if wallet_balance >= total_required:
        wallet_balance -= total_required
        wallet.available = wallet_balance
        credit_used = decimal.Decimal(0)
    else:
        credit_used = total_required - wallet_balance
        wallet.available = decimal.Decimal(0)
        user_locked.credit_used = credit_used_total + credit_used
        credit_available_after = credit_available_before - credit_used

    requires_admin = credit_used > decimal.Decimal(0)

    debited = min(wallet_balance_before, total_required)
    movement = None
    if debited > 0:
        movement = await log_wallet_movement(
            db,
            wallet=wallet,
            user_id=current_user.user_id,
            amount=debited,
            direction=WalletEntryDirectionEnum.DEBIT,
            operation_type="external_transfer",
            reference=data.partner_name,
            description=f"Transfert externe vers {data.recipient_name}",
        )

    bonus_rate = decimal.Decimal(getattr(settings, "BONUS_RATE_MULTIPLIER", "50") or "50")
    bonus_cap = decimal.Decimal(getattr(settings, "BONUS_MAX_PER_TRANSFER", "1000000") or "1000000")
    bonus_earned = min((amount * bonus_rate), bonus_cap)
    transfer_id = uuid.uuid4()
    reference_code = f"EXT-{uuid.uuid4().hex[:8].upper()}"
    wallet.bonus_balance = decimal.Decimal(wallet.bonus_balance or 0) + bonus_earned

    txn_status = "pending"

    txn = Transactions(
        tx_id=transfer_id,
        initiated_by=current_user.user_id,
        channel="external_transfer",
        amount=amount,
        currency_code=origin_currency,
        related_entity_id=transfer_id,
        status=txn_status,
        sender_wallet=wallet.wallet_id,
    )
    db.add(txn)
    await db.flush()

    transfer = ExternalTransfers(
        transfer_id=transfer_id,
        user_id=current_user.user_id,
        partner_name=data.partner_name,
        country_destination=data.country_destination,
        recipient_name=data.recipient_name,
        recipient_phone=data.recipient_phone,
        amount=amount,
        currency=destination_currency,
        rate=fx_rate,
        local_amount=local_amount,
        credit_used=(credit_used > 0),
        status="pending" if requires_admin else "approved",
        processed_by=None,
        processed_at=None,
        reference_code=reference_code,
    )
    db.add(transfer)

    sender_account = await ledger.ensure_wallet_account(wallet)
    try:
        cash_out_account = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CASH_OUT)
    except LookupError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration ledger invalide: {exc}",
        ) from exc
    entries = []
    metadata = {
        "operation": "external_transfer",
        "wallet_id": str(wallet.wallet_id),
        "user_id": str(current_user.user_id),
        "transfer_id": str(transfer.transfer_id),
        "credit_used_amount": str(credit_used),
        "debited_amount": str(debited),
        "transaction_id": str(txn.tx_id),
        "fee_rate": str(fee_rate),
        "fee_amount": str(fee_amount),
        "fx_rate": str(fx_rate),
        "destination_currency": destination_currency,
        "idempotency_key": scoped_idempotency_key,
    }
    if debited > 0:
        entries.append(
            LedgerLine(
                account=sender_account,
                direction="debit",
                amount=debited,
                currency_code=wallet.currency_code,
            )
        )
    if credit_used > 0:
        try:
            credit_account = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CREDIT_LINE)
        except LookupError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Configuration ledger invalide: {exc}",
            ) from exc
        entries.append(
            LedgerLine(
                account=credit_account,
                direction="debit",
                amount=credit_used,
                currency_code=wallet.currency_code,
            )
        )
    entries.append(
        LedgerLine(
            account=cash_out_account,
            direction="credit",
            amount=total_required,
            currency_code=wallet.currency_code,
        )
    )
    if movement:
        metadata["movement_id"] = str(movement.transaction_id)
    metadata = {k: v for k, v in metadata.items() if v is not None}
    await ledger.post_journal(
        tx_id=txn.tx_id,
        description=f"Transfert externe vers {data.recipient_name}",
        metadata=metadata,
        entries=entries,
    )

    db.add(
        BonusHistory(
            user_id=current_user.user_id,
            amount_bif=bonus_earned,
            source="earned",
            reference_id=transfer.transfer_id,
        )
    )

    if credit_used > 0:
        history_entry = CreditLineHistory(
            user_id=current_user.user_id,
            transaction_id=txn.tx_id,
            amount=credit_used,
            credit_available_before=credit_available_before,
            credit_available_after=max(decimal.Decimal("0"), credit_available_after),
            description=f"Transfert externe {transfer.reference_code}",
        )
        db.add(history_entry)

    user_locked.used_daily = decimal.Decimal(user_locked.used_daily or 0) + amount
    user_locked.used_monthly = decimal.Decimal(user_locked.used_monthly or 0) + amount
    await db.commit()
    await db.refresh(transfer)
    if scoped_idempotency_key:
        payload_out = ExternalTransferRead.model_validate(transfer).model_dump(mode="json")
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=payload_out,
        )
        await db.commit()

    await _notify_external_transfer(
        db=db,
        current_user=current_user,
        transfer=transfer,
        data=data,
        amount=amount,
        origin_currency=origin_currency,
        destination_currency=destination_currency,
        local_amount=local_amount,
        credit_used=credit_used,
        credit_available_after=credit_available_after,
        requires_admin=requires_admin,
        fx_rate=fx_rate,
    )
    return payload_out if scoped_idempotency_key else transfer


@router.post("/transfer/external/{transfer_id}/approve")
async def approve_external_transfer(
    transfer_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    transfer = await db.scalar(
        select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id)
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert introuvable")

    transition_external_transfer_status(transfer, "approved")
    transfer.processed_by = current_agent.user_id
    transfer.processed_at = datetime.utcnow()

    txn = await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    if txn:
        txn.status = "pending"
        txn.updated_at = datetime.utcnow()

    await db.commit()
    return {"message": "Transfert valide"}


class InternalTransferRequest(BaseModel):
    paytag: str
    amount: decimal.Decimal


@router.post("/transfer/internal")
async def internal_transfer(
    payload: InternalTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    ledger = LedgerService(db)
    paytag = payload.paytag
    amount = payload.amount
    if amount <= 0:
        raise HTTPException(400, "Montant invalide")

    risk = await update_risk_score(db, current_user, amount, channel="internal")
    if risk >= 80:
        raise HTTPException(423, "Compte gele temporairement pour verification.")

    result = await db.execute(select(Users).where(Users.paytag == paytag))
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(404, "Utilisateur introuvable")

    if receiver.user_id == current_user.user_id:
        raise HTTPException(400, "Vous ne pouvez pas vous envoyer a vous-meme")

    w_sender = (await db.execute(select(Wallets).where(Wallets.user_id == current_user.user_id))).scalar_one()
    w_receiver = (await db.execute(select(Wallets).where(Wallets.user_id == receiver.user_id))).scalar_one()

    if w_sender.available < amount:
        raise HTTPException(400, "Solde insuffisant")

    w_sender.available -= amount
    w_receiver.available += amount

    sender_movement = await log_wallet_movement(
        db,
        wallet=w_sender,
        user_id=current_user.user_id,
        amount=amount,
        direction=WalletEntryDirectionEnum.DEBIT,
        operation_type="internal_transfer_send",
        reference=paytag,
        description=f"Transfert interne vers {paytag}",
    )
    receiver_movement = await log_wallet_movement(
        db,
        wallet=w_receiver,
        user_id=receiver.user_id,
        amount=amount,
        direction=WalletEntryDirectionEnum.CREDIT,
        operation_type="internal_transfer_receive",
        reference=current_user.paytag or current_user.email,
        description=f"Transfert interne recu de {current_user.full_name}",
    )

    tx = Transactions(
        initiated_by=current_user.user_id,
        sender_wallet=w_sender.wallet_id,
        receiver_wallet=w_receiver.wallet_id,
        amount=amount,
        currency_code=w_sender.currency_code,
        channel="internal",
        status="succeeded",
        description=f"Transfert interne vers {paytag}",
    )
    db.add(tx)
    await db.flush()
    sender_account = await ledger.ensure_wallet_account(w_sender)
    receiver_account = await ledger.ensure_wallet_account(w_receiver)
    metadata = {
        "operation": "internal_transfer",
        "sender_wallet_id": str(w_sender.wallet_id),
        "receiver_wallet_id": str(w_receiver.wallet_id),
        "sender_user_id": str(current_user.user_id),
        "receiver_user_id": str(receiver.user_id),
        "paytag": paytag,
        "transaction_id": str(tx.tx_id),
    }
    if sender_movement:
        metadata["sender_movement_id"] = str(sender_movement.transaction_id)
    if receiver_movement:
        metadata["receiver_movement_id"] = str(receiver_movement.transaction_id)
    await ledger.post_journal(
        tx_id=tx.tx_id,
        description=f"Transfert interne vers {paytag}",
        metadata=metadata,
        entries=[
            LedgerLine(
                account=sender_account,
                direction="debit",
                amount=amount,
                currency_code=w_sender.currency_code,
            ),
            LedgerLine(
                account=receiver_account,
                direction="credit",
                amount=amount,
                currency_code=w_receiver.currency_code,
            ),
        ],
    )

    await db.commit()

    await send_transaction_emails(
        db,
        initiator=current_user,
        receiver=receiver,
        subject="Confirmation transfert interne",
        template=None,
        body=f"""
        <p>Votre transfert interne a ete effectue.</p>
        <ul>
          <li>Montant : {amount} {w_sender.currency_code}</li>
          <li>Paytag destinataire : {paytag}</li>
          <li>Statut : reussi</li>
        </ul>
        """,
    )

    return {"message": "success", "tx_id": str(tx.tx_id)}

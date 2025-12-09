import decimal
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
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
from app.schemas.external_transfers import ExternalTransferCreate, ExternalTransferRead
from app.schemas.transactions import TransactionSend
from app.services.aml import update_risk_score
from app.services.ledger import LedgerLine, LedgerService
from app.services.mailer import send_email
from app.services.risk_engine import calculate_risk_score
from app.services.telegram import send_message as send_telegram_message
from app.services.transaction_notifications import send_transaction_emails
from app.services.wallet_history import log_wallet_movement

router = APIRouter(prefix="/wallet/transfer", tags=["External Transfer"])
AGENT_EMAIL = "adolphe.nahimana@yahoo.fr"


@router.post("/external", response_model=ExternalTransferRead)
async def external_transfer(
    data: ExternalTransferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    ledger = LedgerService(db)
    await calculate_risk_score(db, current_user.user_id)

    if current_user.status == "frozen":
        raise HTTPException(423, "Votre compte est gele pour raisons de securite.")

    amount = decimal.Decimal(data.amount)

    result = await db.execute(select(Wallets).where(Wallets.user_id == current_user.user_id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    wallet_balance = decimal.Decimal(wallet.available or 0)
    credit_limit = decimal.Decimal(current_user.credit_limit or 0)
    credit_used_total = decimal.Decimal(current_user.credit_used or 0)
    credit_available = max(credit_limit - credit_used_total, decimal.Decimal(0))
    credit_available_before = credit_available
    total_available = wallet_balance + credit_available

    if amount > total_available:
        raise HTTPException(
            status_code=400,
            detail=f"Montant trop eleve. Disponible total : {total_available} FBU",
        )

    used_daily = decimal.Decimal(current_user.used_daily or 0)
    used_monthly = decimal.Decimal(current_user.used_monthly or 0)
    daily_limit = decimal.Decimal(current_user.daily_limit or 0)
    monthly_limit = decimal.Decimal(current_user.monthly_limit or 0)

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
    rate = decimal.Decimal("7000.0")
    local_amount = amount * rate
    if wallet_balance >= amount:
        wallet_balance -= amount
        wallet.available = wallet_balance
        credit_used = decimal.Decimal(0)
    else:
        credit_used = amount - wallet_balance
        wallet.available = decimal.Decimal(0)
        current_user.credit_used = credit_used_total + credit_used
        credit_available_after = credit_available_before - credit_used

    requires_admin = credit_used > decimal.Decimal(0)

    debited = min(wallet_balance_before, amount)
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

    bonus_earned = amount * decimal.Decimal("50")
    transfer = ExternalTransfers(
        user_id=current_user.user_id,
        partner_name=data.partner_name,
        country_destination=data.country_destination,
        recipient_name=data.recipient_name,
        recipient_phone=data.recipient_phone,
        amount=amount,
        currency="EUR",
        rate=rate,
        local_amount=local_amount,
        credit_used=(credit_used > 0),
        status="pending" if requires_admin else "success",
        processed_by=current_user.user_id,
        processed_at=datetime.now(),
        reference_code=f"EXT-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(transfer)

    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    wallet.bonus_balance += bonus_earned

    txn_status = "pending" if requires_admin else "succeeded"

    txn = Transactions(
        initiated_by=current_user.user_id,
        channel="external_transfer",
        amount=amount,
        currency_code="EUR",
        related_entity_id=transfer.transfer_id,
        status=txn_status,
        sender_wallet=wallet.wallet_id,
    )
    db.add(txn)
    await db.flush()

    sender_account = await ledger.ensure_wallet_account(wallet)
    cash_out_account = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CASH_OUT)
    entries = []
    metadata = {
        "operation": "external_transfer",
        "wallet_id": str(wallet.wallet_id),
        "user_id": str(current_user.user_id),
        "transfer_id": str(transfer.transfer_id),
        "credit_used_amount": str(credit_used),
        "debited_amount": str(debited),
        "transaction_id": str(txn.tx_id),
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
        credit_account = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CREDIT_LINE)
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
            amount=amount,
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

    current_user.used_daily = decimal.Decimal(current_user.used_daily or 0) + amount
    current_user.used_monthly = decimal.Decimal(current_user.used_monthly or 0) + amount
    await db.commit()
    await db.refresh(transfer)

    if requires_admin:
        await run_in_threadpool(
            send_email,
            AGENT_EMAIL,
            f"Nouvelle demande de transfert #{transfer.reference_code}",
            "external_transfer_request_agent.html",
            client_name=current_user.full_name,
            client_email=current_user.email,
            amount=amount,
            currency="EUR",
            payout_amount=f"{local_amount} BIF",
            used_credit=f"{credit_used}EUR",
            recipient_name=data.recipient_name,
            recipient_phone=data.recipient_phone,
            partner="Lumicash",
            country="Burundi",
        )

        chat_ids = (await db.execute(select(TelegramUser.chat_id))).scalars().all()
        telegram_message = (
            "Nouvelle demande de transfert externe\n"
            f"Client: {current_user.full_name} ({current_user.email})\n"
            f"Montant: {amount} EUR\n"
            f"Destinataire: {data.recipient_name} ({data.recipient_phone})\n"
            f"Partenaire: {data.partner_name}\n"
            f"Reference: {transfer.reference_code}"
        )
        for chat_id in chat_ids:
            try:
                await send_telegram_message(int(chat_id), telegram_message)
            except Exception:
                continue

    await send_transaction_emails(
        db,
        initiator=current_user,
        subject=f"Nouvelle demande de transfert {transfer.reference_code}",
        template="external_transfer_request_agent.html",
        client_name=current_user.full_name,
        client_email=current_user.email,
        client_phone=current_user.phone_e164 or "",
        amount=amount,
        currency="EUR",
        payout_amount=f"{local_amount} BIF",
        credit_available=f"{credit_available_after}",
        receiver_name=data.recipient_name,
        receiver_phone=data.recipient_phone,
        partner_name=data.partner_name,
        country=data.country_destination,
        transfer_id=transfer.reference_code,
        dashboard_url=f"{settings.FRONTEND_URL}/dashboard/admin",
        year=datetime.utcnow().year,
    )

    return transfer


@router.post("/transfer/external/{transfer_id}/approve")
async def approve_external_transfer(
    transfer_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    transfer = await db.scalar(select(ExternalTransfers).where(ExternalTransfers.id == transfer_id))

    transfer.status = "approved"
    transfer.processed_by = current_agent.user_id
    transfer.processed_at = datetime.utcnow()

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

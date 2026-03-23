import decimal
import logging
import uuid
from datetime import datetime
from datetime import timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker, get_db
from app.dependencies.auth import get_current_agent, get_current_user
from app.models.bonus_history import BonusHistory
from app.models.credit_line_history import CreditLineHistory
from app.models.credit_line_events import CreditLineEvents
from app.models.credit_lines import CreditLines
from app.models.countries import Countries
from app.models.external_transfers import ExternalTransfers
from app.models.telegram_user import TelegramUser
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.agents import Agents
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
from app.services.risk_engine import calculate_risk_score
from app.services.mailjet_service import MailjetEmailService
from app.services.telegram import send_message as send_telegram_message
from app.services.transaction_notifications import send_transaction_emails
from app.services.wallet_history import log_wallet_movement
from app.services.pdf_utils import build_external_transfer_receipt


def _normalize_optional_email(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        # Response model expects a valid email; legacy free-text values should not 500 the route.
        return str(EmailStr(raw))
    except Exception:
        return None
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


async def _get_destination_currency(db: AsyncSession, country: str) -> str:
    """
    Resolve the destination currency from paylink.countries; fallback to EUR.
    """
    raw_country = str(country or "").strip()
    if not raw_country:
        return "EUR"

    country_row = await db.scalar(
        select(Countries).where(text("lower(name) = :country_name")).params(
            country_name=raw_country.lower()
        )
    )
    if country_row and country_row.currency_code:
        return str(country_row.currency_code).upper()
    return "EUR"


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
    async def _resolve_exact_rate(source: str, target: str) -> decimal.Decimal | None:
        if source == target:
            return decimal.Decimal("1")

        if source == "BIF" or target == "BIF":
            custom = await db.scalar(
                select(FxCustomRates)
                .where(
                    FxCustomRates.origin_currency == source,
                    FxCustomRates.destination_currency == target,
                    FxCustomRates.is_active.is_(True),
                )
                .order_by(FxCustomRates.updated_at.desc())
            )
            if custom and custom.rate:
                return decimal.Decimal(custom.rate)

        fx_row = await db.scalar(
            select(FxConversions.rate_used)
            .where(
                FxConversions.from_currency == source,
                FxConversions.to_currency == target,
            )
            .order_by(FxConversions.created_at.desc())
            .limit(1)
        )
        if fx_row:
            return decimal.Decimal(fx_row)
        return None

    if origin == destination:
        return decimal.Decimal("1")

    if destination == "BIF" and origin != "EUR":
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"https://api.exchangerate.host/convert?from={origin}&to=EUR"
                )
            if res.status_code != 200:
                raise HTTPException(status_code=500, detail="Erreur API ExchangeRate")
            data = res.json()
            source_to_eur = data.get("info", {}).get("rate")
        except HTTPException:
            raise
        except Exception:
            source_to_eur = None

        eur_to_bif = await _resolve_exact_rate("EUR", "BIF")
        if source_to_eur not in (None, 0) and eur_to_bif is not None:
            return decimal.Decimal(str(source_to_eur)) * eur_to_bif
        raise HTTPException(
            status_code=400,
            detail=f"Taux introuvable pour la conversion {origin}->EUR puis EUR->BIF",
        )

    exact_rate = await _resolve_exact_rate(origin, destination)
    if exact_rate is not None:
        return exact_rate

    if origin != "EUR" and destination != "EUR":
        to_eur_rate = await _resolve_exact_rate(origin, "EUR")
        from_eur_rate = await _resolve_exact_rate("EUR", destination)
        if to_eur_rate is not None and from_eur_rate is not None:
            return to_eur_rate * from_eur_rate

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


async def _list_external_transfer_agent_users(db: AsyncSession) -> list[Users]:
    rows = await db.execute(
        select(Agents, Users)
        .join(Users, Users.user_id == Agents.user_id, isouter=True)
        .where(
            Agents.active.is_(True),
            Agents.email.is_not(None),
        )
    )
    agents: list[Users] = []
    seen_emails: set[str] = set()
    for agent_row, user_row in rows.all():
        email = str(agent_row.email or getattr(user_row, "email", "") or "").strip().lower()
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        agents.append(
            user_row
            if user_row is not None
            else Users(
                user_id=agent_row.user_id,
                email=email,
                full_name=str(agent_row.display_name or "Agent PesaPaid").strip() or "Agent PesaPaid",
            )
        )
    return agents


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
    override_context: dict | None = None,
) -> None:
    agent_users = await _list_external_transfer_agent_users(db)
    agent_mailer: MailjetEmailService | None = None
    try:
        agent_mailer = MailjetEmailService()
    except Exception as exc:
        logger.exception(
            "Agent notification mailer initialization failed for external transfer %s: %s",
            transfer.transfer_id,
            exc,
        )
    explicit_agent_email = _normalize_optional_email(
        (override_context or {}).get("notify_agent_email")
    )
    explicit_agent_name = str((override_context or {}).get("notify_agent_name") or "").strip()
    if explicit_agent_email:
        known_emails = {str(agent.email or "").strip().lower() for agent in agent_users if agent.email}
        if explicit_agent_email.lower() not in known_emails:
            agent_users.append(
                Users(
                    email=explicit_agent_email,
                    full_name=explicit_agent_name or "Agent PesaPaid",
                )
            )
    logger.info(
        "External transfer notifications prepared transfer_id=%s agent_recipients=%s client_email=%s recipient_email=%s",
        transfer.transfer_id,
        [str(agent.email) for agent in agent_users if getattr(agent, "email", None)],
        current_user.email,
        data.recipient_email,
    )
    backend_base = str(getattr(settings, "BACKEND_URL", "") or "").strip()
    for agent_user in agent_users:
        if agent_mailer is None:
            break
        close_link = None
        if backend_base and requires_admin:
            close_token = create_access_token(
                data={
                    "sub": str(agent_user.user_id),
                    "action": "external_transfer_close_by_agent_link",
                    "transfer_id": str(transfer.transfer_id),
                },
                expires_delta=timedelta(hours=48),
            )
            close_link = (
                f"{backend_base.rstrip('/')}/agent/external/{transfer.transfer_id}"
                f"/close-by-link?token={close_token}"
            )
        try:
            await run_in_threadpool(
                agent_mailer.send_email,
                str(agent_user.email),
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
                "Agent notification email failed for external transfer %s to %s: %s",
                transfer.transfer_id,
                agent_user.email,
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

    if current_user.email:
        try:
            await send_transaction_emails(
                db,
                initiator=current_user,
                subject=f"Demande de transfert {transfer.reference_code}",
                template="external_transfer_request_client.html",
                recipients=[current_user.email],
                client_name=current_user.full_name or "",
                amount=str(amount),
                currency=origin_currency,
                payout_amount=f"{local_amount} {destination_currency}",
                receiver_name=data.recipient_name,
                receiver_phone=data.recipient_phone,
                partner_name=data.partner_name,
                country=data.country_destination,
                transfer_id=transfer.reference_code,
                status=transfer.status,
                year=datetime.utcnow().year,
            )
        except Exception as exc:
            logger.exception(
                "Client request notification failed for external transfer %s: %s",
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

    if data.recipient_email:
        try:
            await send_transaction_emails(
                db,
                initiator=current_user,
                subject=f"Transfert PesaPaid {transfer.reference_code}",
                recipients=[data.recipient_email],
                template="external_transfer_recipient_notification.html",
                recipient_name=data.recipient_name,
                sender_name=current_user.full_name or "Client PesaPaid",
                reference=transfer.reference_code,
                payout_amount=f"{local_amount} {destination_currency}",
                receiver_phone=data.recipient_phone,
                partner_name=data.partner_name,
                country=data.country_destination,
                status=transfer.status,
                year=datetime.utcnow().year,
            )
        except Exception as exc:
            logger.exception(
                "Recipient notification email failed for external transfer %s: %s",
                transfer.transfer_id,
                exc,
            )


async def _notify_external_transfer_task(
    *,
    current_user_id: str,
    transfer_id: str,
    data_payload: dict,
    amount: str,
    origin_currency: str,
    destination_currency: str,
    local_amount: str,
    credit_used: str,
    credit_available_after: str,
    requires_admin: bool,
    fx_rate: str,
    override_context: dict | None = None,
) -> None:
    try:
        async with async_session_maker() as db:
            current_user = await db.scalar(
                select(Users).where(Users.user_id == UUID(str(current_user_id)))
            )
            transfer = await db.scalar(
                select(ExternalTransfers).where(ExternalTransfers.transfer_id == UUID(str(transfer_id)))
            )
            if not current_user or not transfer:
                logger.warning(
                    "Skip external transfer notifications: current_user=%s transfer=%s missing",
                    current_user_id,
                    transfer_id,
                )
                return
            await _notify_external_transfer(
                db=db,
                current_user=current_user,
                transfer=transfer,
                data=ExternalTransferCreate(**data_payload),
                amount=decimal.Decimal(amount),
                origin_currency=origin_currency,
                destination_currency=destination_currency,
                local_amount=decimal.Decimal(local_amount),
                credit_used=decimal.Decimal(credit_used),
                credit_available_after=decimal.Decimal(credit_available_after),
                requires_admin=requires_admin,
                fx_rate=decimal.Decimal(fx_rate),
                override_context=override_context,
            )
    except Exception as exc:
        logger.exception(
            "Background external transfer notification failed for transfer %s: %s",
            transfer_id,
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
          "recipient_email": None,
          "partner_name": r.partner_name,
          "country_destination": r.country_destination,
        }
        for r in rows
    ]


async def _external_transfer_core(
    data: ExternalTransferCreate,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
    override_balance_check: bool = False,
    override_context: dict | None = None,
    final_status_override: str | None = None,
    processed_by_user_id: str | None = None,
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
                "recipient_email": str(data.recipient_email or "").strip().lower(),
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
    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == current_user.user_id,
            CreditLines.deleted_at.is_(None),
        )
        .order_by(CreditLines.created_at.desc())
        .with_for_update()
    )
    if credit_line:
        credit_limit = decimal.Decimal(credit_line.initial_amount or 0)
        credit_used_total = decimal.Decimal(credit_line.used_amount or 0)
        credit_available = max(decimal.Decimal(credit_line.outstanding_amount or 0), decimal.Decimal(0))
    else:
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
    destination_currency = await _get_destination_currency(db, data.country_destination)
    fx_rate = await _resolve_fx_rate(db, origin_currency, destination_currency)

    total_required = amount + fee_amount
    total_available = wallet_balance + credit_available
    force_negative_wallet = override_balance_check and total_required > total_available

    if total_required > total_available and not override_balance_check:
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
    wallet_after = wallet_balance_before
    if wallet_balance_before >= total_required:
        wallet_after = wallet_balance_before - total_required
        wallet.available = wallet_after
        credit_used = decimal.Decimal(0)
    else:
        wallet_consumed = max(wallet_balance_before, decimal.Decimal("0"))
        remaining_after_wallet = total_required - wallet_consumed
        credit_used = min(credit_available_before, remaining_after_wallet)
        credit_available_after = credit_available_before - credit_used
        residual_after_credit = remaining_after_wallet - credit_used
        wallet_after = -residual_after_credit if force_negative_wallet else decimal.Decimal("0")
        wallet.available = wallet_after
        if credit_line:
            credit_line.used_amount = decimal.Decimal(credit_line.used_amount or 0) + credit_used
            credit_line.outstanding_amount = max(decimal.Decimal("0"), credit_available_after)
            credit_line.updated_at = datetime.utcnow()
            user_locked.credit_limit = decimal.Decimal(credit_line.initial_amount or 0)
            user_locked.credit_used = decimal.Decimal(credit_line.used_amount or 0)
        else:
            user_locked.credit_used = credit_used_total + credit_used

    requires_admin = credit_used > decimal.Decimal(0)
    requested_status = str(final_status_override or "").strip().lower()
    if requested_status == "completed":
        transfer_status = "completed"
        txn_status = "completed"
    elif requested_status == "approved":
        transfer_status = "approved"
        txn_status = "pending"
    else:
        transfer_status = "pending" if requires_admin else "approved"
        txn_status = "pending"

    debited = wallet_balance_before - wallet_after
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
        status=transfer_status,
        processed_by=processed_by_user_id if transfer_status == "completed" else None,
        processed_at=datetime.utcnow() if transfer_status == "completed" else None,
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
        "override_balance_check": bool(override_balance_check),
        "force_negative_wallet": bool(force_negative_wallet),
        "final_status_override": requested_status or None,
        "processed_by_user_id": processed_by_user_id if transfer_status == "completed" else None,
    }
    if override_context and isinstance(override_context, dict):
        metadata["override_context"] = {
            str(key): str(value)
            for key, value in override_context.items()
            if value is not None
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
        credit_account = await ledger.ensure_system_account(
            code=settings.LEDGER_ACCOUNT_CREDIT_LINE,
            name="Ligne de credit clients",
            currency_code=wallet.currency_code,
            metadata={"kind": "system", "purpose": "credit_line"},
        )
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
        if credit_line:
            db.add(
                CreditLineEvents(
                    credit_line_id=credit_line.credit_line_id,
                    user_id=current_user.user_id,
                    amount_delta=credit_used,
                    currency_code=credit_line.currency_code,
                    old_limit=credit_available_before,
                    new_limit=max(decimal.Decimal("0"), credit_available_after),
                    operation_code=9101,
                    status="used",
                    source="external_transfer",
                    occurred_at=datetime.utcnow(),
                )
            )

    user_locked.used_daily = decimal.Decimal(user_locked.used_daily or 0) + amount
    user_locked.used_monthly = decimal.Decimal(user_locked.used_monthly or 0) + amount
    if credit_line and credit_used <= decimal.Decimal("0"):
        user_locked.credit_limit = decimal.Decimal(credit_line.initial_amount or 0)
        user_locked.credit_used = decimal.Decimal(credit_line.used_amount or 0)
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

    notification_kwargs = {
        "current_user_id": str(current_user.user_id),
        "transfer_id": str(transfer.transfer_id),
        "data_payload": data.model_dump(mode="json"),
        "amount": str(amount),
        "origin_currency": origin_currency,
        "destination_currency": destination_currency,
        "local_amount": str(local_amount),
        "credit_used": str(credit_used),
        "credit_available_after": str(credit_available_after),
        "requires_admin": requires_admin,
        "fx_rate": str(fx_rate),
        "override_context": override_context,
    }
    background_tasks.add_task(_notify_external_transfer_task, **notification_kwargs)
    return payload_out if scoped_idempotency_key else transfer


@router.post("/external", response_model=ExternalTransferRead)
async def external_transfer(
    data: ExternalTransferCreate,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await _external_transfer_core(
        data=data,
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        current_user=current_user,
    )


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

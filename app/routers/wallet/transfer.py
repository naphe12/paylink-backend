import decimal
import logging
import re
import uuid
from datetime import date
from datetime import datetime
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import case, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker, get_db
from app.dependencies.auth import get_current_agent, get_current_user
from app.models.bonus_history import BonusHistory
from app.models.credit_line_history import CreditLineHistory
from app.models.credit_line_events import CreditLineEvents
from app.models.credit_lines import CreditLines
from app.models.countries import Countries
from app.models.external_beneficiaries import ExternalBeneficiaries
from app.models.external_transfers import ExternalTransfers
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
from app.services.aml import update_risk_score
from app.services.ledger import LedgerLine, LedgerService
from app.services.risk_engine import calculate_risk_score
from app.services.mailjet_service import MailjetEmailService
from app.services.telegram import send_message as send_telegram_message
from app.services.transaction_notifications import send_transaction_emails
from app.services.wallet_history import log_wallet_movement
from app.services.pdf_utils import build_external_transfer_receipt
from app.services.external_transfer_capacity import (
    compute_external_transfer_funding,
    effective_external_transfer_capacity,
)
from app.services.external_transfer_limits import (
    build_user_external_transfer_limit_analysis,
    normalize_external_transfer_limit_policy,
)


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
from app.core.security import create_access_token, decode_access_token
from app.services.payment_note_service import (
    build_external_transfer_payment_note_pdf,
    build_external_transfer_payment_note_png,
    build_payment_instruction_sentence,
    format_note_amount,
    resolve_payment_instruction,
)
from app.services.external_transfer_rules import (
    map_external_transfer_to_transaction_status,
    transition_external_transfer_status,
)
from app.services.fx_provider import get_open_exchange_rate_to_eur

router = APIRouter(prefix="/wallet/transfer", tags=["External Transfer"])
logger = logging.getLogger(__name__)
EXTERNAL_TRANSFER_PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")
AML_ALERT_THRESHOLD = 50
AML_MANUAL_REVIEW_THRESHOLD = 60
AML_AUTO_FREEZE_THRESHOLD = 80
EXTERNAL_TRANSFER_SETTLEMENT_CURRENCY = "BIF"


def _is_valid_external_phone(value: str | None) -> bool:
    return bool(EXTERNAL_TRANSFER_PHONE_RE.fullmatch(str(value or "").strip()))


def _refresh_user_limits_counters_inplace(user: Users) -> None:
    """Reset daily/monthly counters when the period changed, without committing."""
    today = date.today()
    last_reset = getattr(user, "last_reset", None)
    if last_reset != today:
        user.used_daily = decimal.Decimal("0")
    if last_reset is None or (last_reset.year, last_reset.month) != (today.year, today.month):
        user.used_monthly = decimal.Decimal("0")
    user.last_reset = today


def _primary_wallet_for_update_stmt(user_id):
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
        .with_for_update()
    )


def _primary_wallet_stmt(user_id):
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
    )


def _serialize_decimal(value: decimal.Decimal | None) -> float:
    return float(value or 0)


class ExternalTransferSimulationRequest(BaseModel):
    amount: decimal.Decimal = Field(..., gt=decimal.Decimal("0"), le=decimal.Decimal("100000000"))
    currency: str | None = Field(default=None, min_length=3, max_length=10)

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        raw = str(value or "").strip().upper()
        if not raw:
            raise ValueError("currency invalide")
        return raw


def _derive_external_transfer_aml_reason_codes(
    *,
    user: Users,
    amount: decimal.Decimal,
    risk_score: int,
    channel: str,
) -> list[str]:
    codes: list[str] = []
    kyc_tier = int(getattr(user, "kyc_tier", 0) or 0)
    if kyc_tier <= 0:
        codes.append("AML_KYC_UNVERIFIED")
    elif kyc_tier == 1:
        codes.append("AML_KYC_BASIC")

    created_at = getattr(user, "created_at", None)
    if created_at is not None:
        user_age_days = max((datetime.utcnow() - created_at.replace(tzinfo=None) if getattr(created_at, "tzinfo", None) else datetime.utcnow() - created_at).days, 0)
        if user_age_days < 7:
            codes.append("AML_NEW_ACCOUNT_LT_7D")
        elif user_age_days < 30:
            codes.append("AML_NEW_ACCOUNT_LT_30D")

    if amount >= decimal.Decimal("1000000"):
        codes.append("AML_AMOUNT_GE_1000000")
    elif amount >= decimal.Decimal("300000"):
        codes.append("AML_AMOUNT_GE_300000")

    if str(channel or "").lower() == "external":
        codes.append("AML_EXTERNAL_CHANNEL")

    if risk_score >= AML_AUTO_FREEZE_THRESHOLD:
        codes.append("AML_SCORE_CRITICAL")
    elif risk_score >= AML_MANUAL_REVIEW_THRESHOLD:
        codes.append("AML_SCORE_MANUAL_REVIEW")
    elif risk_score >= AML_ALERT_THRESHOLD:
        codes.append("AML_SCORE_ALERT")

    return codes


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


async def _get_sender_country_currency(
    db: AsyncSession,
    user: Users,
    fallback_currency: str | None = None,
) -> str:
    user_country_code = str(getattr(user, "country_code", "") or "").strip()
    if user_country_code:
        country_currency = await db.scalar(
            select(Countries.currency_code).where(Countries.country_code == user_country_code)
        )
        if country_currency:
            return str(country_currency).upper()
    return str(fallback_currency or "EUR").upper()


async def _build_payment_note_context(
    db: AsyncSession,
    *,
    transfer: ExternalTransfers,
    current_user: Users,
    amount: decimal.Decimal,
    origin_currency: str,
    data: ExternalTransferCreate,
) -> dict | None:
    metadata = dict(transfer.metadata_ or {})
    instruction = await resolve_payment_instruction(
        db,
        user=current_user,
        origin_currency=origin_currency,
    )
    if not instruction:
        return None

    fee_amount = decimal.Decimal(str(metadata.get("fee_amount") or "0"))
    total_payment_amount = amount + fee_amount
    payment_sentence = build_payment_instruction_sentence(
        amount=total_payment_amount,
        currency=origin_currency,
        account_service=instruction["account_service"],
    )
    backend_base = str(getattr(settings, "BACKEND_URL", "") or "").strip()
    payment_note_url = None
    if backend_base:
        note_token = create_access_token(
            data={
                "sub": str(current_user.user_id),
                "action": "external_transfer_payment_note",
                "transfer_id": str(transfer.transfer_id),
            },
            expires_delta=timedelta(days=14),
        )
        payment_note_url = (
            f"{backend_base.rstrip('/')}/wallet/transfer/external/{transfer.transfer_id}/payment-note.png"
            f"?token={note_token}"
        )

    note_payload = {
        "reference_code": transfer.reference_code or str(transfer.transfer_id),
        "client_name": current_user.full_name or "",
        "recipient_name": data.recipient_name,
        "country_destination": data.country_destination,
        "sent_amount_text": format_note_amount(amount, origin_currency),
        "fee_amount_text": format_note_amount(fee_amount, origin_currency),
        "amount_text": format_note_amount(total_payment_amount, origin_currency),
        "recipient_amount_text": format_note_amount(
            transfer.local_amount or amount,
            str(metadata.get("destination_currency") or EXTERNAL_TRANSFER_SETTLEMENT_CURRENCY or "BIF"),
        ),
        "payment_sentence": payment_sentence,
        "service": instruction["service"],
        "account_service": instruction["account_service"],
        "account_country_code": instruction["country_code"],
        "payment_currency": instruction["payment_currency"],
    }
    return {
        "instruction": instruction,
        "payment_sentence": payment_sentence,
        "payment_note_url": payment_note_url,
        "note_payload": note_payload,
        "note_filename": f"note-paiement-{transfer.reference_code or transfer.transfer_id}.png",
        "note_pdf_filename": f"note-paiement-{transfer.reference_code or transfer.transfer_id}.pdf",
    }


def _serialize_external_transfer_read(transfer: ExternalTransfers) -> dict:
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    return ExternalTransferRead.model_validate(
        {
            "transfer_id": transfer.transfer_id,
            "user_id": transfer.user_id,
            "partner_name": transfer.partner_name,
            "country_destination": transfer.country_destination,
            "recipient_name": transfer.recipient_name,
            "recipient_phone": str(transfer.recipient_phone or "").strip() or None,
            "recipient_email": _normalize_optional_email(metadata.get("recipient_email")),
            "amount": transfer.amount,
            "currency": str(metadata.get("origin_currency") or "EUR"),
            "rate": transfer.rate,
            "local_amount": transfer.local_amount,
            "credit_used": transfer.credit_used,
            "status": transfer.status,
            "reference_code": transfer.reference_code,
            "created_at": transfer.created_at,
        }
    ).model_dump(mode="json")


def _is_payment_note_required(
    *,
    transfer: ExternalTransfers | None = None,
    metadata: dict | None = None,
    credit_used: decimal.Decimal | None = None,
    wallet_available: decimal.Decimal | None = None,
) -> bool:
    payload = dict(metadata or getattr(transfer, "metadata_", {}) or {})
    stored_flag = payload.get("payment_note_required")
    if stored_flag is not None:
        return bool(stored_flag)
    if credit_used is not None and credit_used > decimal.Decimal("0"):
        return True
    if wallet_available is not None and wallet_available < decimal.Decimal("0"):
        return True
    return bool(getattr(transfer, "credit_used", False))


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
        source_to_eur = await get_open_exchange_rate_to_eur(origin)
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


def _is_truthy_flag(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


async def _list_external_transfer_agent_users(db: AsyncSession) -> list[Users]:
    rows = await db.execute(
        select(Agents, Users)
        .join(Users, Users.user_id == Agents.user_id, isouter=True)
        .where(
            Agents.active.is_(True),
            or_(
                Agents.email.is_not(None),
                Users.email.is_not(None),
            ),
        )
    )
    agents: list[Users] = []
    seen_emails: set[str] = set()
    for agent_row, user_row in rows.all():
        agent_email = str(getattr(agent_row, "email", "") or "").strip().lower()
        user_email = str(getattr(user_row, "email", "") or "").strip().lower()
        email = agent_email or user_email
        if not email:
            logger.info(
                "External transfer agent recipient skipped user_id=%s display_name=%s reason=missing_email",
                agent_row.user_id,
                agent_row.display_name,
            )
            continue
        if email in seen_emails:
            logger.info(
                "External transfer agent recipient skipped user_id=%s display_name=%s email=%s reason=duplicate_email",
                agent_row.user_id,
                agent_row.display_name,
                email,
            )
            continue
        seen_emails.add(email)
        agents.append(
            Users(
                user_id=agent_row.user_id,
                email=email,
                full_name=(
                    str(getattr(user_row, "full_name", "") or "").strip()
                    or str(agent_row.display_name or "Agent PesaPaid").strip()
                    or "Agent PesaPaid"
                ),
            )
        )
    logger.info(
        "External transfer agent recipients resolved count=%s emails=%s",
        len(agents),
        [str(agent.email) for agent in agents if getattr(agent, "email", None)],
    )
    return agents


async def _load_telegram_chat_ids_for_user_ids(
    db: AsyncSession,
    user_ids: list[str],
) -> list[str]:
    chat_ids: list[str] = []
    seen_chat_ids: set[str] = set()
    for user_id in user_ids:
        candidate = str(user_id or "").strip()
        if not candidate:
            continue
        row = (
            await db.execute(
                text(
                    """
                    SELECT chat_id
                    FROM paylink.telegram_chat_links
                    WHERE user_id = CAST(:user_id AS uuid)
                    LIMIT 1
                    """
                ),
                {"user_id": candidate},
            )
        ).mappings().first()
        chat_id = str((row or {}).get("chat_id") or "").strip()
        if not chat_id or chat_id in seen_chat_ids:
            continue
        seen_chat_ids.add(chat_id)
        chat_ids.append(chat_id)
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
    override_context: dict | None = None,
    notify_agents: bool = True,
    notify_telegram: bool = True,
    notify_client: bool = True,
    notify_recipient: bool = True,
) -> None:
    agent_users: list[Users] = []
    if notify_agents:
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
        configured_agent_email = _normalize_optional_email(getattr(settings, "AGENT_EMAIL", None))
        if configured_agent_email:
            known_emails = {str(agent.email or "").strip().lower() for agent in agent_users if agent.email}
            if configured_agent_email.lower() not in known_emails:
                agent_users.append(
                    Users(
                        email=configured_agent_email,
                        full_name="Agent PesaPaid",
                    )
                )
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

    if notify_telegram:
        if not agent_users:
            agent_users = await _list_external_transfer_agent_users(db)
        linked_chat_ids = await _load_telegram_chat_ids_for_user_ids(
            db,
            [
                str(getattr(agent_user, "user_id", "") or "").strip()
                for agent_user in agent_users
            ],
        )
        configured_chat_ids = [str(chat_id) for chat_id in _parse_telegram_notify_chat_ids()]
        chat_ids = linked_chat_ids or configured_chat_ids
        context = dict(override_context or {})
        source_label = str(context.get("source") or "").strip()
        via_assistant = source_label == "agent_chat_web"
        telegram_message = (
            f"{'Nouvelle demande assistant transfert' if via_assistant else 'Nouveau transfert externe'}\n"
            f"Client: {current_user.full_name}\n"
            f"Montant: {amount} {origin_currency}\n"
            f"Pays: {data.country_destination}\n"
            f"Partenaire: {data.partner_name}\n"
            f"Beneficiaire: {data.recipient_name}\n"
            f"Telephone: {data.recipient_phone}\n"
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

    payment_note_context = None
    should_send_payment_note = False
    if notify_client and current_user.email:
        client_wallet = await db.scalar(
            select(Wallets)
            .where(Wallets.user_id == current_user.user_id)
            .order_by(
                case(
                    (Wallets.type == "personal", 0),
                    (Wallets.type == "consumer", 1),
                    else_=2,
                ),
                Wallets.wallet_id.asc(),
            )
            .limit(1)
        )
        client_wallet_available = decimal.Decimal(getattr(client_wallet, "available", 0) or 0)
        should_send_payment_note = _is_payment_note_required(
            transfer=transfer,
            metadata=dict(transfer.metadata_ or {}),
            credit_used=credit_used,
            wallet_available=client_wallet_available,
        )

    if notify_client and current_user.email and should_send_payment_note:
        payment_note_context = await _build_payment_note_context(
            db,
            transfer=transfer,
            current_user=current_user,
            amount=amount,
            origin_currency=origin_currency,
            data=data,
        )

    if notify_client and current_user.email:
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
                payment_instruction_sentence=(
                    payment_note_context["payment_sentence"] if payment_note_context else None
                ),
                payment_account_display=(
                    payment_note_context["instruction"]["account_display"] if payment_note_context else None
                ),
                payment_note_url=(
                    payment_note_context["payment_note_url"] if payment_note_context else None
                ),
                year=datetime.utcnow().year,
            )
        except Exception as exc:
            logger.exception(
                "Client request notification failed for external transfer %s: %s",
                transfer.transfer_id,
                exc,
            )

    if notify_client and current_user.email:
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
        note_bytes = (
            build_external_transfer_payment_note_pdf(payment_note_context["note_payload"])
            if payment_note_context
            else None
        )
        attachments = [{"name": f"recu-{transfer.reference_code}.pdf", "content": receipt_bytes}]
        if note_bytes and payment_note_context:
            attachments.append(
                {
                    "name": payment_note_context["note_pdf_filename"],
                    "content": note_bytes,
                    "content_type": "application/pdf",
                }
            )
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
                payment_instruction_sentence=(
                    payment_note_context["payment_sentence"] if payment_note_context else None
                ),
                payment_account_display=(
                    payment_note_context["instruction"]["account_display"] if payment_note_context else None
                ),
                payment_note_url=(
                    payment_note_context["payment_note_url"] if payment_note_context else None
                ),
                year=datetime.utcnow().year,
                attachments=attachments,
            )
        except Exception as exc:
            logger.exception(
                "Receipt email failed for external transfer %s: %s",
                transfer.transfer_id,
                exc,
            )

    if notify_recipient and data.recipient_email:
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
    notify_agents: bool = True,
    notify_telegram: bool = True,
    notify_client: bool = True,
    notify_recipient: bool = True,
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
                notify_agents=notify_agents,
                notify_telegram=notify_telegram,
                notify_client=notify_client,
                notify_recipient=notify_recipient,
            )
    except Exception as exc:
        logger.exception(
            "Background external transfer notification failed for transfer %s: %s",
            transfer_id,
            exc,
        )


@router.get("/external/{transfer_id}/payment-note.png")
async def download_external_transfer_payment_note(
    transfer_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_access_token(token)
    if payload.get("action") != "external_transfer_payment_note":
        raise HTTPException(status_code=403, detail="Token invalide pour cette note")
    if str(payload.get("transfer_id") or "") != str(transfer_id):
        raise HTTPException(status_code=403, detail="Token transfer mismatch")

    transfer = await db.scalar(
        select(ExternalTransfers).where(ExternalTransfers.transfer_id == UUID(str(transfer_id)))
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert introuvable")

    if str(payload.get("sub") or "") != str(transfer.user_id):
        raise HTTPException(status_code=403, detail="Token utilisateur invalide")

    current_user = await db.scalar(select(Users).where(Users.user_id == transfer.user_id))
    if not current_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    metadata = dict(transfer.metadata_ or {})
    origin_currency = str(metadata.get("origin_currency") or transfer.currency or "EUR").upper()
    transfer_data = ExternalTransferCreate(
        partner_name=transfer.partner_name,
        country_destination=transfer.country_destination,
        recipient_name=transfer.recipient_name,
        recipient_phone=transfer.recipient_phone,
        recipient_email=_normalize_optional_email(metadata.get("recipient_email")),
        amount=decimal.Decimal(transfer.amount or 0),
    )
    payment_note_context = await _build_payment_note_context(
        db,
        transfer=transfer,
        current_user=current_user,
        amount=decimal.Decimal(transfer.amount or 0),
        origin_currency=origin_currency,
        data=transfer_data,
    )
    if not payment_note_context:
        raise HTTPException(status_code=404, detail="Informations de paiement introuvables")

    note_bytes = build_external_transfer_payment_note_png(payment_note_context["note_payload"])
    filename = payment_note_context["note_filename"]
    return Response(
        content=note_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/external/beneficiaries")
async def list_external_beneficiaries(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Liste des bénéficiaires déjà utilisés par l'utilisateur pour ses transferts externes.
    """
    transfer_stmt = (
        select(
            ExternalTransfers.recipient_name,
            ExternalTransfers.recipient_phone,
            ExternalTransfers.metadata_.label("metadata_"),
            ExternalTransfers.partner_name,
            ExternalTransfers.country_destination,
        )
        .where(ExternalTransfers.user_id == current_user.user_id)
        .distinct()
        .order_by(ExternalTransfers.recipient_name.asc())
    )
    saved_stmt = (
        select(ExternalBeneficiaries)
        .where(
            ExternalBeneficiaries.user_id == current_user.user_id,
            ExternalBeneficiaries.is_active.is_(True),
        )
        .order_by(ExternalBeneficiaries.recipient_name.asc())
    )
    transfer_rows = (await db.execute(transfer_stmt)).all()
    saved_rows = (await db.execute(saved_stmt)).scalars().all()

    beneficiaries: dict[tuple[str, str, str], dict] = {}
    for item in saved_rows:
        phone = str(item.recipient_phone or "").strip()
        if not _is_valid_external_phone(phone):
            continue
        account_ref = str(item.recipient_email or "").strip().lower()
        beneficiaries[(str(item.partner_name or "").strip().lower(), phone, account_ref)] = {
            "recipient_name": item.recipient_name,
            "recipient_phone": phone or None,
            "account_ref": account_ref or None,
            "recipient_email": str(item.recipient_email or "").strip().lower() or None,
            "partner_name": item.partner_name,
            "country_destination": item.country_destination,
        }

    for row in transfer_rows:
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
            },
        )
    return sorted(beneficiaries.values(), key=lambda item: (str(item.get("recipient_name") or "").lower(), str(item.get("partner_name") or "").lower()))


@router.get("/external/mine")
async def list_my_external_transfers(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    safe_limit = max(1, min(int(limit or 10), 50))
    result = await db.execute(
        select(ExternalTransfers)
        .where(ExternalTransfers.user_id == current_user.user_id)
        .order_by(ExternalTransfers.created_at.desc())
        .limit(safe_limit)
    )
    return [
        _serialize_external_transfer_read(transfer)
        for transfer in result.scalars().all()
        if _is_valid_external_phone(transfer.recipient_phone)
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
    execute_notifications_inline: bool = False,
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
    if not _is_valid_external_phone(data.recipient_phone):
        raise HTTPException(status_code=400, detail="Numero beneficiaire invalide")

    user_locked = await db.scalar(
        select(Users).where(Users.user_id == current_user.user_id).with_for_update()
    )
    if not user_locked:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    _refresh_user_limits_counters_inplace(user_locked)
    if user_locked.status == "frozen":
        raise HTTPException(423, "Votre compte est gele pour raisons de securite.")
    wallet = await db.scalar(_primary_wallet_for_update_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    wallet_balance = decimal.Decimal(wallet.available or 0)
    wallet_currency = str(wallet.currency_code or "").upper()
    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == current_user.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
        .with_for_update()
    )
    credit_line_currency = str(getattr(credit_line, "currency_code", "") or "").upper()
    if wallet_currency and credit_line_currency and wallet_currency != credit_line_currency:
        raise HTTPException(
            status_code=400,
            detail=(
                "Devise incoherente entre portefeuille et ligne de credit. "
                "Le transfert externe doit etre finance dans une devise unique."
            ),
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
    origin_currency = wallet_currency or credit_line_currency or "EUR"
    is_bif_wallet = str(wallet.currency_code or "").upper() == "BIF"
    destination_currency = EXTERNAL_TRANSFER_SETTLEMENT_CURRENCY
    if is_bif_wallet and str(destination_currency or "").upper() == "BIF":
        fee_rate = decimal.Decimal("6.25")
    else:
        settings_row = await db.scalar(
            select(GeneralSettings).order_by(GeneralSettings.created_at.desc())
        )
        fee_rate = decimal.Decimal(getattr(settings_row, "charge", 0) or 0)
    fee_amount = (amount * fee_rate / decimal.Decimal(100)).quantize(decimal.Decimal("0.01"))

    fx_rate = await _resolve_fx_rate(db, origin_currency, destination_currency)

    total_required = amount + fee_amount
    approval_available = (
        credit_available
        if is_bif_wallet
        else effective_external_transfer_capacity(wallet_balance, credit_available)
    )
    insufficient_funds_review_required = total_required > approval_available and not override_balance_check
    shortfall_amount = max(decimal.Decimal("0"), total_required - approval_available)

    used_daily = decimal.Decimal(user_locked.used_daily or 0)
    used_monthly = decimal.Decimal(user_locked.used_monthly or 0)
    daily_limit = decimal.Decimal(user_locked.daily_limit or 0)
    monthly_limit = decimal.Decimal(user_locked.monthly_limit or 0)
    external_limit_policy = normalize_external_transfer_limit_policy(
        getattr(settings, "EXTERNAL_TRANSFER_LIMIT_POLICY", None)
    )

    limit_analysis = await build_user_external_transfer_limit_analysis(
        db,
        user_id=user_locked.user_id,
        current_daily_limit=daily_limit,
        current_monthly_limit=monthly_limit,
        kyc_tier=int(getattr(user_locked, "kyc_tier", 0) or 0),
        risk_score=int(getattr(user_locked, "risk_score", 0) or 0),
    )
    recommendation = (limit_analysis or {}).get("recommendation") or {}
    recommended_daily = decimal.Decimal(str(recommendation.get("recommended_daily_limit") or "0"))
    recommended_monthly = decimal.Decimal(str(recommendation.get("recommended_monthly_limit") or "0"))
    effective_daily_limit = daily_limit
    effective_monthly_limit = monthly_limit
    if external_limit_policy == "dynamic":
        if recommended_daily > 0:
            effective_daily_limit = max(effective_daily_limit, recommended_daily)
        if recommended_monthly > 0:
            effective_monthly_limit = max(effective_monthly_limit, recommended_monthly)

    if external_limit_policy != "financial_capacity_only":
        if effective_daily_limit > 0 and amount + used_daily > effective_daily_limit:
            raise HTTPException(
                400,
                (
                    "Limite journaliere atteinte sur transfert externe. "
                    f"Montant demande: {amount}. Utilise aujourd'hui: {used_daily}. "
                    f"Plafond journalier effectif: {effective_daily_limit}. "
                    f"Politique active: {external_limit_policy}."
                ),
            )

        if effective_monthly_limit > 0 and amount + used_monthly > effective_monthly_limit:
            raise HTTPException(
                400,
                (
                    "Limite mensuelle atteinte sur transfert externe. "
                    f"Montant demande: {amount}. Utilise ce mois: {used_monthly}. "
                    f"Plafond mensuel effectif: {effective_monthly_limit}. "
                    f"Politique active: {external_limit_policy}."
                ),
            )

    risk = await update_risk_score(
        db,
        current_user,
        amount,
        channel="external",
        autocommit=False,
    )
    aml_manual_review_required = risk >= 60
    aml_reason_codes = _derive_external_transfer_aml_reason_codes(
        user=user_locked,
        amount=amount,
        risk_score=int(risk),
        channel="external",
    )

    if current_user.external_transfers_blocked:
        raise HTTPException(423, "Transferts externes temporairement suspendus.")

    wallet_balance_before = wallet_balance
    credit_available_after = credit_available_before
    local_amount = (amount * fx_rate).quantize(decimal.Decimal("0.01"))
    wallet_after = wallet_balance_before
    credit_used = decimal.Decimal("0")
    wallet_debit_amount = decimal.Decimal("0")
    if not insufficient_funds_review_required:
        funding = compute_external_transfer_funding(
            wallet_available=wallet_balance_before,
            credit_available=credit_available_before,
            total_required=total_required,
            prefer_credit_only=is_bif_wallet,
            mirror_wallet_with_credit=not is_bif_wallet,
        )
        wallet_after = funding["wallet_after"]
        credit_used = funding["credit_used"]
        credit_available_after = funding["credit_available_after"]
        wallet_debit_amount = funding["wallet_debit_amount"]
        wallet.available = wallet_after
        if credit_line:
            credit_line.used_amount = decimal.Decimal(credit_line.used_amount or 0) + credit_used
            credit_line.outstanding_amount = max(decimal.Decimal("0"), credit_available_after)
            credit_line.updated_at = datetime.utcnow()
            user_locked.credit_limit = decimal.Decimal(credit_line.initial_amount or 0)
            user_locked.credit_used = decimal.Decimal(credit_line.used_amount or 0)
        else:
            user_locked.credit_used = credit_used_total + credit_used

    review_reasons: list[str] = []
    if insufficient_funds_review_required:
        review_reasons.append("insufficient_funds")
    if aml_manual_review_required:
        review_reasons.append("aml")

    requires_admin = (
        aml_manual_review_required
        or insufficient_funds_review_required
    )
    requested_status = str(final_status_override or "").strip().lower()
    if requires_admin:
        transfer_status = "pending"
        txn_status = map_external_transfer_to_transaction_status(transfer_status)
    elif requested_status == "completed":
        transfer_status = "completed"
        txn_status = map_external_transfer_to_transaction_status(transfer_status)
    elif requested_status == "approved":
        transfer_status = "approved"
        txn_status = map_external_transfer_to_transaction_status(transfer_status)
    else:
        transfer_status = "pending" if requires_admin else "approved"
        txn_status = map_external_transfer_to_transaction_status(transfer_status)

    debited = wallet_debit_amount
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
    if not insufficient_funds_review_required:
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
        currency=origin_currency,
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
        cash_out_account = await ledger.get_cash_out_account(wallet.currency_code)
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
        "credit_available_after": str(credit_available_after),
        "debited_amount": str(debited),
        "transaction_id": str(txn.tx_id),
        "fee_rate": str(fee_rate),
        "fee_amount": str(fee_amount),
        "fx_rate": str(fx_rate),
        "origin_currency": origin_currency,
        "destination_currency": destination_currency,
        "idempotency_key": scoped_idempotency_key,
        "override_balance_check": bool(override_balance_check),
        "force_negative_wallet": bool(override_balance_check),
        "final_status_override": requested_status or None,
        "processed_by_user_id": processed_by_user_id if transfer_status == "completed" else None,
        "aml_risk_score": int(risk),
        "aml_manual_review_required": bool(aml_manual_review_required),
        "aml_reason_codes": aml_reason_codes or None,
        "review_reason": review_reasons[0] if review_reasons else None,
        "review_reasons": review_reasons or None,
        "funding_pending": bool(insufficient_funds_review_required),
        "required_credit_topup": str(shortfall_amount) if insufficient_funds_review_required else None,
        "total_required": str(total_required),
        "recipient_email": data.recipient_email,
        "wallet_balance_after_transfer": str(wallet_after),
        "payment_note_required": bool(
            credit_used > decimal.Decimal("0") or wallet_after < decimal.Decimal("0")
        ),
        "external_transfer_limit_policy": external_limit_policy,
        "effective_daily_limit": str(effective_daily_limit),
        "effective_monthly_limit": str(effective_monthly_limit),
        "recommended_daily_limit": str(recommended_daily),
        "recommended_monthly_limit": str(recommended_monthly),
    }
    if override_context and isinstance(override_context, dict):
        metadata["override_context"] = {
            str(key): str(value)
            for key, value in override_context.items()
            if value is not None
        }
    if not insufficient_funds_review_required:
        if debited > 0:
            entries.append(
                LedgerLine(
                    account=sender_account,
                    direction="debit",
                    amount=debited,
                    currency_code=wallet.currency_code,
                )
            )
        # Keep journal balanced even when funding logic mirrors wallet debit with credit exposure.
        ledger_credit_component = max(decimal.Decimal("0"), total_required - debited)
        if ledger_credit_component > 0:
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
                    amount=ledger_credit_component,
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
    transfer.metadata_ = metadata
    if entries:
        await ledger.post_journal(
            tx_id=txn.tx_id,
            description=f"Transfert externe vers {data.recipient_name}",
            metadata=metadata,
            entries=entries,
        )

    if not insufficient_funds_review_required:
        db.add(
            BonusHistory(
                user_id=current_user.user_id,
                amount_bif=bonus_earned,
                source="earned",
                reference_id=transfer.transfer_id,
            )
        )

    if not insufficient_funds_review_required and credit_used > 0:
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
                    amount_delta=-credit_used,
                    currency_code=credit_line.currency_code,
                    old_limit=credit_available_before,
                    new_limit=max(decimal.Decimal("0"), credit_available_after),
                    operation_code=9101,
                    status="used",
                    source="external_transfer",
                    occurred_at=datetime.utcnow(),
                )
            )

    if not insufficient_funds_review_required:
        user_locked.used_daily = decimal.Decimal(user_locked.used_daily or 0) + amount
        user_locked.used_monthly = decimal.Decimal(user_locked.used_monthly or 0) + amount
        if credit_line and credit_used <= decimal.Decimal("0"):
            user_locked.credit_limit = decimal.Decimal(credit_line.initial_amount or 0)
            user_locked.credit_used = decimal.Decimal(credit_line.used_amount or 0)
    await db.flush()
    await db.refresh(transfer)
    payload_out = _serialize_external_transfer_read(transfer)
    if scoped_idempotency_key:
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
        "notify_agents": transfer_status in {"pending", "approved"},
        "notify_telegram": transfer_status in {"pending", "approved"}
        or _is_truthy_flag((override_context or {}).get("notify_telegram_on_create")),
        "notify_client": True,
        "notify_recipient": transfer_status == "approved",
    }
    if execute_notifications_inline:
        try:
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
                override_context=override_context,
                notify_agents=notification_kwargs["notify_agents"],
                notify_telegram=notification_kwargs["notify_telegram"],
                notify_client=notification_kwargs["notify_client"],
                notify_recipient=notification_kwargs["notify_recipient"],
            )
        except Exception as exc:
            logger.exception(
                "Inline external transfer notification failed transfer_id=%s user_id=%s: %s",
                transfer.transfer_id,
                current_user.user_id,
                exc,
            )
    else:
        background_tasks.add_task(_notify_external_transfer_task, **notification_kwargs)
    return payload_out if scoped_idempotency_key else payload_out


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


@router.post("/external/simulate")
async def simulate_external_transfer(
    payload: ExternalTransferSimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        return {
            "possible": False,
            "reasons": ["Portefeuille principal introuvable."],
            "refusal_reasons": ["wallet_not_found"],
        }

    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == current_user.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
    )

    wallet_balance = decimal.Decimal(wallet.available or 0)
    wallet_currency = str(wallet.currency_code or "EUR").upper()
    credit_available = (
        max(decimal.Decimal(credit_line.outstanding_amount or 0), decimal.Decimal("0"))
        if credit_line
        else max(
            decimal.Decimal(current_user.credit_limit or 0)
            - decimal.Decimal(current_user.credit_used or 0),
            decimal.Decimal("0"),
        )
    )
    credit_currency = (
        str(credit_line.currency_code or wallet_currency).upper()
        if credit_line
        else wallet_currency
    )
    sender_currency = await _get_sender_country_currency(db, current_user, wallet_currency)
    requested_currency = str(payload.currency or sender_currency).upper()
    is_bif_wallet = wallet_currency == "BIF"
    destination_currency = EXTERNAL_TRANSFER_SETTLEMENT_CURRENCY

    if is_bif_wallet and destination_currency == "BIF":
        fee_rate = decimal.Decimal("6.25")
    else:
        settings_row = await db.scalar(select(GeneralSettings).order_by(GeneralSettings.created_at.desc()))
        fee_rate = decimal.Decimal(getattr(settings_row, "charge", 0) or 0)
    fee_amount = (payload.amount * fee_rate / decimal.Decimal(100)).quantize(decimal.Decimal("0.01"))
    total_required = payload.amount + fee_amount

    fx_rate = await _resolve_fx_rate(db, sender_currency, destination_currency)
    local_amount = (payload.amount * fx_rate).quantize(decimal.Decimal("0.01"))

    approval_capacity = (
        credit_available
        if is_bif_wallet
        else effective_external_transfer_capacity(wallet_balance, credit_available)
    )
    funding = compute_external_transfer_funding(
        wallet_available=wallet_balance,
        credit_available=credit_available,
        total_required=total_required,
        prefer_credit_only=is_bif_wallet,
        mirror_wallet_with_credit=not is_bif_wallet,
    )
    capacity_after = (
        funding["credit_available_after"]
        if is_bif_wallet
        else effective_external_transfer_capacity(
            funding["wallet_after"],
            funding["credit_available_after"],
        )
    )

    reasons: list[str] = []
    refusal_reasons: list[str] = []
    if requested_currency != sender_currency:
        refusal_reasons.append("currency_mismatch")
        reasons.append(
            f"Devise demandee {requested_currency} non compatible: ce client transfere en {sender_currency}."
        )
    if total_required > approval_capacity:
        refusal_reasons.append("insufficient_capacity")
        shortfall = (total_required - approval_capacity).quantize(decimal.Decimal("0.01"))
        reasons.append(
            f"Capacite insuffisante: il manque {shortfall} {wallet_currency} pour couvrir montant + frais."
        )
    if is_bif_wallet:
        reasons.append("Regle wallet BIF: seule la ligne de credit finance le transfert externe.")
    elif credit_available > decimal.Decimal("0"):
        reasons.append(
            "Regle standard: le wallet est debite du total (montant + frais), "
            "et la ligne de credit couvre uniquement la part en wallet negatif."
        )
    else:
        reasons.append("Aucune ligne de credit active: le wallet supporte integralement le total (montant + frais).")

    return {
        "possible": len(refusal_reasons) == 0,
        "reasons": reasons,
        "refusal_reasons": refusal_reasons,
        "user": {
            "user_id": str(current_user.user_id),
            "full_name": current_user.full_name,
            "email": current_user.email,
        },
        "rule": {
            "wallet_bif_credit_only": is_bif_wallet,
            "sender_currency": sender_currency,
            "requested_currency": requested_currency,
            "destination_currency": destination_currency,
        },
        "amounts": {
            "amount": _serialize_decimal(payload.amount),
            "fee_rate": _serialize_decimal(fee_rate),
            "fee_amount": _serialize_decimal(fee_amount),
            "total_required": _serialize_decimal(total_required),
            "fx_rate": _serialize_decimal(fx_rate),
            "local_amount": _serialize_decimal(local_amount),
        },
        "before": {
            "wallet_balance": _serialize_decimal(wallet_balance),
            "wallet_currency": wallet_currency,
            "credit_available": _serialize_decimal(credit_available),
            "credit_currency": credit_currency,
            "financial_capacity": _serialize_decimal(approval_capacity),
        },
        "after": {
            "wallet_balance": _serialize_decimal(funding["wallet_after"]),
            "wallet_currency": wallet_currency,
            "credit_available": _serialize_decimal(funding["credit_available_after"]),
            "credit_currency": credit_currency,
            "financial_capacity": _serialize_decimal(capacity_after),
        },
    }


@router.get("/external/limits-insights")
async def get_my_external_transfer_limits_insights(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    user = await db.scalar(select(Users).where(Users.user_id == current_user.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    _refresh_user_limits_counters_inplace(user)

    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille principal introuvable")

    wallet_balance = decimal.Decimal(wallet.available or 0)
    wallet_currency = str(wallet.currency_code or "EUR").upper()
    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == current_user.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
    )
    credit_available = (
        max(decimal.Decimal(credit_line.outstanding_amount or 0), decimal.Decimal("0"))
        if credit_line
        else max(
            decimal.Decimal(user.credit_limit or 0) - decimal.Decimal(user.credit_used or 0),
            decimal.Decimal("0"),
        )
    )
    financial_capacity = effective_external_transfer_capacity(wallet_balance, credit_available)

    current_daily = decimal.Decimal(user.daily_limit or 0)
    current_monthly = decimal.Decimal(user.monthly_limit or 0)
    used_daily = decimal.Decimal(user.used_daily or 0)
    used_monthly = decimal.Decimal(user.used_monthly or 0)
    policy = normalize_external_transfer_limit_policy(
        getattr(settings, "EXTERNAL_TRANSFER_LIMIT_POLICY", None)
    )
    analysis = await build_user_external_transfer_limit_analysis(
        db,
        user_id=user.user_id,
        current_daily_limit=current_daily,
        current_monthly_limit=current_monthly,
        kyc_tier=int(getattr(user, "kyc_tier", 0) or 0),
        risk_score=int(getattr(user, "risk_score", 0) or 0),
    )
    recommendation = (analysis or {}).get("recommendation") or {}
    recommended_daily = decimal.Decimal(str(recommendation.get("recommended_daily_limit") or "0"))
    recommended_monthly = decimal.Decimal(str(recommendation.get("recommended_monthly_limit") or "0"))

    effective_daily = current_daily
    effective_monthly = current_monthly
    if policy == "dynamic":
        if recommended_daily > 0:
            effective_daily = max(effective_daily, recommended_daily)
        if recommended_monthly > 0:
            effective_monthly = max(effective_monthly, recommended_monthly)
    if effective_monthly > 0:
        effective_monthly = max(effective_monthly, effective_daily)

    blockers: list[str] = []
    next_steps: list[str] = []
    if str(getattr(user, "status", "")).lower() == "frozen":
        blockers.append("account_frozen")
        next_steps.append("Contacte le support pour verifier la securite du compte.")
    if bool(getattr(user, "external_transfers_blocked", False)):
        blockers.append("external_transfers_blocked")
        next_steps.append("Demande la levee de blocage transfert externe au support.")
    if str(getattr(user, "kyc_status", "unverified")).lower() != "verified":
        blockers.append("kyc_not_verified")
        next_steps.append("Complete la verification KYC pour debloquer les transferts externes.")
    if int(getattr(user, "risk_score", 0) or 0) >= AML_AUTO_FREEZE_THRESHOLD:
        blockers.append("risk_too_high")
        next_steps.append("Un controle de conformite est necessaire avant de reprendre les transferts.")
    if financial_capacity <= decimal.Decimal("0"):
        blockers.append("insufficient_financial_capacity")
        next_steps.append("Ajoute du solde ou reduis le montant du prochain transfert.")

    blocked_now = len(blockers) > 0
    if blocked_now:
        primary_blocker = blockers[0]
        simple_message = "Transfert externe temporairement bloque. Consulte la raison principale ci-dessous."
    elif policy == "financial_capacity_only":
        primary_blocker = "none"
        simple_message = "Aucun blocage de limite. Seule ta capacite financiere sera verifiee."
    else:
        primary_blocker = "none"
        simple_message = "Aucun blocage en cours. Tes limites sont adaptees selon ton historique."

    remaining_daily = None
    remaining_monthly = None
    if policy != "financial_capacity_only":
        remaining_daily = max(effective_daily - used_daily, decimal.Decimal("0"))
        remaining_monthly = max(effective_monthly - used_monthly, decimal.Decimal("0"))

    # De-duplicate while keeping order.
    next_steps = list(dict.fromkeys(next_steps))
    if not next_steps:
        next_steps.append("Tu peux continuer les transferts externes normalement.")

    return {
        "policy_mode": policy,
        "blocked_now": blocked_now,
        "primary_blocker": primary_blocker,
        "blocked_reasons": blockers,
        "simple_message": simple_message,
        "next_steps": next_steps,
        "financial_capacity": {
            "wallet_balance": _serialize_decimal(wallet_balance),
            "credit_available": _serialize_decimal(credit_available),
            "capacity": _serialize_decimal(financial_capacity),
            "currency": wallet_currency,
        },
        "limits": {
            "current_daily_limit": _serialize_decimal(current_daily),
            "current_monthly_limit": _serialize_decimal(current_monthly),
            "effective_daily_limit": _serialize_decimal(effective_daily),
            "effective_monthly_limit": _serialize_decimal(effective_monthly),
            "used_daily": _serialize_decimal(used_daily),
            "used_monthly": _serialize_decimal(used_monthly),
            "remaining_daily": _serialize_decimal(remaining_daily) if remaining_daily is not None else None,
            "remaining_monthly": _serialize_decimal(remaining_monthly) if remaining_monthly is not None else None,
            "recommended_daily_limit": _serialize_decimal(recommended_daily),
            "recommended_monthly_limit": _serialize_decimal(recommended_monthly),
            "recommended_per_tx": _serialize_decimal(decimal.Decimal(str(recommendation.get("recommended_per_tx") or "0"))),
            "recommendation_confidence": recommendation.get("confidence"),
            "recommendation_confidence_score": recommendation.get("confidence_score"),
            "recommendation_calculation_inputs": recommendation.get("calculation_inputs") or {},
            "recommendation_explanations": recommendation.get("explanations") or [],
        },
        "history": (analysis or {}).get("history") or {},
    }


async def _fund_pending_external_transfer_for_approval(
    db: AsyncSession,
    *,
    transfer: ExternalTransfers,
) -> None:
    metadata = dict(transfer.metadata_ or {})
    if not metadata.get("funding_pending"):
        return

    user = await db.scalar(
        select(Users).where(Users.user_id == transfer.user_id).with_for_update()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    wallet = await db.scalar(_primary_wallet_for_update_stmt(transfer.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == transfer.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
        .with_for_update()
    )

    total_required = decimal.Decimal(str(metadata.get("total_required") or "0"))
    if total_required <= decimal.Decimal("0"):
        raise HTTPException(status_code=400, detail="Montant de financement invalide")

    wallet_balance_before = decimal.Decimal(wallet.available or 0)
    is_bif_wallet = str(wallet.currency_code or "").upper() == "BIF"
    credit_available_before = (
        max(decimal.Decimal(credit_line.outstanding_amount or 0), decimal.Decimal("0"))
        if credit_line
        else decimal.Decimal("0")
    )
    approval_available_before = (
        credit_available_before
        if is_bif_wallet
        else effective_external_transfer_capacity(wallet_balance_before, credit_available_before)
    )
    shortage = max(decimal.Decimal("0"), total_required - approval_available_before)
    now = datetime.utcnow()

    if shortage > 0:
        if credit_line is None:
            origin_currency = str(metadata.get("origin_currency") or wallet.currency_code or "EUR").upper()
            credit_line = CreditLines(
                user_id=transfer.user_id,
                currency_code=origin_currency,
                initial_amount=shortage,
                used_amount=decimal.Decimal("0"),
                outstanding_amount=shortage,
                status="active",
                source="external_transfer_approval",
                created_at=now,
                updated_at=now,
            )
            db.add(credit_line)
            await db.flush()
            db.add(
                CreditLineEvents(
                    credit_line_id=credit_line.credit_line_id,
                    user_id=transfer.user_id,
                    amount_delta=shortage,
                    currency_code=credit_line.currency_code,
                    old_limit=decimal.Decimal("0"),
                    new_limit=shortage,
                    operation_code=9000,
                    status="created",
                    source="external_transfer_approval",
                    occurred_at=now,
                )
            )
        else:
            old_limit = decimal.Decimal(credit_line.initial_amount or 0)
            old_outstanding = decimal.Decimal(credit_line.outstanding_amount or 0)
            credit_line.initial_amount = old_limit + shortage
            credit_line.outstanding_amount = old_outstanding + shortage
            credit_line.updated_at = now
            db.add(
                CreditLineEvents(
                    credit_line_id=credit_line.credit_line_id,
                    user_id=transfer.user_id,
                    amount_delta=shortage,
                    currency_code=credit_line.currency_code,
                    old_limit=old_outstanding,
                    new_limit=decimal.Decimal(credit_line.outstanding_amount or 0),
                    operation_code=9001,
                    status="updated",
                    source="external_transfer_approval",
                    occurred_at=now,
                )
            )

    credit_available_before = (
        max(decimal.Decimal(credit_line.outstanding_amount or 0), decimal.Decimal("0"))
        if credit_line
        else decimal.Decimal("0")
    )
    funding = compute_external_transfer_funding(
        wallet_available=wallet_balance_before,
        credit_available=credit_available_before,
        total_required=total_required,
        prefer_credit_only=is_bif_wallet,
        mirror_wallet_with_credit=not is_bif_wallet,
    )
    credit_used = funding["credit_used"]
    credit_available_after = funding["credit_available_after"]
    wallet_debit_amount = funding["wallet_debit_amount"]
    wallet_after = funding["wallet_after"]

    wallet.available = wallet_after
    if credit_line:
        credit_line.used_amount = decimal.Decimal(credit_line.used_amount or 0) + credit_used
        credit_line.outstanding_amount = max(decimal.Decimal("0"), credit_available_after)
        credit_line.updated_at = now
        user.credit_limit = decimal.Decimal(credit_line.initial_amount or 0)
        user.credit_used = decimal.Decimal(credit_line.used_amount or 0)

    debited = wallet_debit_amount
    movement = None
    if debited > 0:
        movement = await log_wallet_movement(
            db,
            wallet=wallet,
            user_id=user.user_id,
            amount=debited,
            direction=WalletEntryDirectionEnum.DEBIT,
            operation_type="external_transfer",
            reference=transfer.reference_code,
            description=f"Transfert externe approuve {transfer.reference_code}",
        )

    txn = await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction liee introuvable")

    ledger = LedgerService(db)
    sender_account = await ledger.ensure_wallet_account(wallet)
    cash_out_account = await ledger.get_cash_out_account(wallet.currency_code)
    entries = []
    if debited > 0:
        entries.append(
            LedgerLine(
                account=sender_account,
                direction="debit",
                amount=debited,
                currency_code=wallet.currency_code,
            )
        )
    # Keep journal balanced even when funding logic mirrors wallet debit with credit exposure.
    ledger_credit_component = max(decimal.Decimal("0"), total_required - debited)
    if ledger_credit_component > 0:
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
                amount=ledger_credit_component,
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

    metadata.update(
        {
            "funding_pending": False,
            "required_credit_topup": str(shortage),
            "credit_used_amount": str(credit_used),
            "debited_amount": str(debited),
            "approval_funded_at": now.isoformat(),
        }
    )
    if movement:
        metadata["movement_id"] = str(movement.transaction_id)
    transfer.credit_used = credit_used > 0
    transfer.metadata_ = {k: v for k, v in metadata.items() if v is not None}

    await ledger.post_journal(
        tx_id=txn.tx_id,
        description=f"Financement transfert externe {transfer.reference_code}",
        metadata=transfer.metadata_,
        entries=entries,
    )

    bonus_rate = decimal.Decimal(getattr(settings, "BONUS_RATE_MULTIPLIER", "50") or "50")
    bonus_cap = decimal.Decimal(getattr(settings, "BONUS_MAX_PER_TRANSFER", "1000000") or "1000000")
    bonus_earned = min((decimal.Decimal(transfer.amount or 0) * bonus_rate), bonus_cap)
    wallet.bonus_balance = decimal.Decimal(wallet.bonus_balance or 0) + bonus_earned
    db.add(
        BonusHistory(
            user_id=user.user_id,
            amount_bif=bonus_earned,
            source="earned",
            reference_id=transfer.transfer_id,
        )
    )

    if credit_used > 0 and credit_line:
        db.add(
            CreditLineHistory(
                user_id=user.user_id,
                transaction_id=txn.tx_id,
                amount=credit_used,
                credit_available_before=credit_available_before,
                credit_available_after=max(decimal.Decimal("0"), credit_available_after),
                description=f"Transfert externe {transfer.reference_code}",
            )
        )
        db.add(
            CreditLineEvents(
                credit_line_id=credit_line.credit_line_id,
                user_id=user.user_id,
                amount_delta=-credit_used,
                currency_code=credit_line.currency_code,
                old_limit=credit_available_before,
                new_limit=max(decimal.Decimal("0"), credit_available_after),
                operation_code=9101,
                status="used",
                source="external_transfer",
                occurred_at=now,
            )
        )

    # Keep daily/monthly counters aligned with the current period at approval time.
    _refresh_user_limits_counters_inplace(user)
    user.used_daily = decimal.Decimal(user.used_daily or 0) + decimal.Decimal(transfer.amount or 0)
    user.used_monthly = decimal.Decimal(user.used_monthly or 0) + decimal.Decimal(transfer.amount or 0)
    txn.status = map_external_transfer_to_transaction_status(transfer.status)
    txn.updated_at = now


@router.post("/transfer/external/{transfer_id}/approve")
async def approve_external_transfer(
    transfer_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if str(getattr(current_user, "role", "") or "").lower() not in {"agent", "admin"}:
        raise HTTPException(status_code=403, detail="Acces refuse")

    transfer = await db.scalar(
        select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id)
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert introuvable")

    pre_approval_metadata = dict(transfer.metadata_ or {})
    was_funding_pending = bool(pre_approval_metadata.get("funding_pending"))

    await _fund_pending_external_transfer_for_approval(db, transfer=transfer)

    transition_external_transfer_status(transfer, "approved")
    transfer.processed_by = current_user.user_id
    transfer.processed_at = datetime.utcnow()

    txn = await db.scalar(
        select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
    )
    if txn:
        txn.status = map_external_transfer_to_transaction_status(transfer.status)
        txn.updated_at = datetime.utcnow()

    await db.commit()

    initiator = await db.scalar(select(Users).where(Users.user_id == transfer.user_id))
    if initiator:
        transfer_payload = {
            "partner_name": transfer.partner_name,
            "country_destination": transfer.country_destination,
            "recipient_name": transfer.recipient_name,
            "recipient_phone": transfer.recipient_phone,
            "recipient_email": (transfer.metadata_ or {}).get("recipient_email"),
            "amount": str(transfer.amount),
        }
        transfer_metadata = transfer.metadata_ or {}
        requires_admin_notification = bool(
            transfer.credit_used
            or transfer_metadata.get("aml_manual_review_required")
            or transfer_metadata.get("funding_pending")
        )
        background_tasks.add_task(
            _notify_external_transfer_task,
            current_user_id=str(initiator.user_id),
            transfer_id=str(transfer.transfer_id),
            data_payload=transfer_payload,
            amount=str(transfer.amount),
            origin_currency=str(
                transfer_metadata.get("origin_currency")
                or getattr(txn, "currency_code", None)
                or "EUR"
            ),
            destination_currency=str(
                transfer_metadata.get("destination_currency")
                or EXTERNAL_TRANSFER_SETTLEMENT_CURRENCY
                or "EUR"
            ),
            local_amount=str(transfer.local_amount or transfer.amount),
            credit_used=str(
                transfer_metadata.get("credit_used_amount")
                or (transfer.amount if transfer.credit_used else "0")
            ),
            credit_available_after=str(transfer_metadata.get("credit_available_after") or "0"),
            requires_admin=requires_admin_notification,
            fx_rate=str(transfer.rate or transfer_metadata.get("fx_rate") or "1"),
            override_context=transfer_metadata.get("override_context"),
            notify_agents=True,
            notify_telegram=True,
            notify_client=was_funding_pending,
            notify_recipient=True,
        )
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

    w_sender = await db.scalar(_primary_wallet_for_update_stmt(current_user.user_id))
    w_receiver = await db.scalar(_primary_wallet_for_update_stmt(receiver.user_id))
    if not w_sender or not w_receiver:
        raise HTTPException(404, "Portefeuille introuvable")
    if str(w_sender.currency_code or "").upper() != str(w_receiver.currency_code or "").upper():
        raise HTTPException(
            400,
            "Transfert interne impossible entre portefeuilles de devises differentes.",
        )

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

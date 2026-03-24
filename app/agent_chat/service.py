from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_chat.parser import parse_chat_message
from app.agent_chat.schemas import ChatResponse, TransferDraft
from app.models.wallets import Wallets


SUPPORTED_TRANSFER_PARTNERS = {"Lumicash", "Ecocash", "eNoti"}


async def _get_wallet_currency(db: AsyncSession, user_id) -> str | None:
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user_id))
    if not wallet or not wallet.currency_code:
        return None
    return str(wallet.currency_code).upper()


def _missing_fields_for_confirmation(draft: TransferDraft) -> list[str]:
    missing = []
    if draft.amount is None or draft.amount <= Decimal("0"):
        missing.append("amount")
    if not draft.currency:
        missing.append("currency")
    if not draft.recipient:
        missing.append("recipient")
    return missing


def _missing_fields_for_execution(draft: TransferDraft) -> list[str]:
    missing = []
    if not draft.partner_name:
        missing.append("partner_name")
    if not draft.country_destination:
        missing.append("country_destination")
    if not draft.recipient_phone:
        missing.append("recipient_phone")
    return missing


async def process_chat_message(db: AsyncSession, *, user_id, message: str) -> ChatResponse:
    draft = parse_chat_message(message)
    if not draft.currency:
        draft.currency = await _get_wallet_currency(db, user_id)

    missing = _missing_fields_for_confirmation(draft)
    if missing:
        return ChatResponse(
            status="NEED_INFO",
            message="Je peux preparer le transfert, mais il me manque le montant, la devise ou le beneficiaire.",
            data=draft,
            missing_fields=missing,
            executable=False,
        )

    executable = (
        not _missing_fields_for_execution(draft)
        and str(draft.partner_name or "") in SUPPORTED_TRANSFER_PARTNERS
    )
    partner_text = f" via {draft.partner_name}" if draft.partner_name else ""
    return ChatResponse(
        status="CONFIRM",
        message=(
            f"Confirmer l'envoi de {draft.amount} {draft.currency} a {draft.recipient}{partner_text} ?"
        ),
        data=draft,
        missing_fields=_missing_fields_for_execution(draft) if not executable else [],
        executable=executable,
    )


def cancel_chat_request() -> ChatResponse:
    return ChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)

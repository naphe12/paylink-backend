import decimal

from sqlalchemy import cast, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit_chat.parser import parse_credit_message
from app.credit_chat.schemas import CreditChatResponse, CreditDraft
from app.models.credit_lines import CreditLines
from app.models.external_transfers import ExternalTransfers
from app.models.general_settings import GeneralSettings
from app.models.wallets import Wallets


async def _get_wallet_context(db: AsyncSession, user_id) -> dict:
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user_id))
    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
    )
    wallet_currency = str(getattr(wallet, "currency_code", "") or "").upper() or "EUR"
    wallet_available = decimal.Decimal(getattr(wallet, "available", 0) or 0)
    credit_available = (
        max(decimal.Decimal(getattr(credit_line, "outstanding_amount", 0) or 0), decimal.Decimal("0"))
        if credit_line
        else decimal.Decimal("0")
    )
    return {
        "wallet_currency": wallet_currency,
        "wallet_available": wallet_available,
        "credit_available": credit_available,
        "total_capacity": wallet_available + credit_available,
    }


async def _resolve_fee_rate(db: AsyncSession, currency: str) -> decimal.Decimal:
    if str(currency or "").upper() == "BIF":
        return decimal.Decimal("6.25")
    settings_row = await db.scalar(select(GeneralSettings).order_by(GeneralSettings.created_at.desc()))
    return decimal.Decimal(getattr(settings_row, "charge", 0) or 0)


async def _get_latest_pending_transfer(db: AsyncSession, user_id):
    return await db.scalar(
        select(ExternalTransfers)
        .where(
            ExternalTransfers.user_id == user_id,
            cast(ExternalTransfers.status, String).in_(("pending", "initiated")),
        )
        .order_by(ExternalTransfers.created_at.desc())
    )


def _build_suggestions(draft: CreditDraft, missing: list[str]) -> list[str]:
    suggestions: list[str] = []
    if draft.intent == "unknown":
        suggestions.extend(
            [
                "Demande la capacite financiere actuelle.",
                "Demande le credit disponible restant.",
                "Demande si un montant peut passer, par exemple 200 USD.",
                "Demande pourquoi une demande de transfert est pending.",
            ]
        )
    if "amount" in missing:
        suggestions.append("Precise le montant, par exemple 200 USD.")
    if "currency" in missing:
        suggestions.append("Precise la devise, par exemple BIF ou USD.")
    return suggestions[:6]


async def process_credit_message(db: AsyncSession, *, user_id, message: str) -> CreditChatResponse:
    draft = parse_credit_message(message)
    wallet_ctx = await _get_wallet_context(db, user_id)
    draft.wallet_currency = wallet_ctx["wallet_currency"]
    if not draft.currency:
        draft.currency = wallet_ctx["wallet_currency"]

    summary = {
        "wallet_currency": wallet_ctx["wallet_currency"],
        "wallet_available": str(wallet_ctx["wallet_available"]),
        "credit_available": str(wallet_ctx["credit_available"]),
        "total_capacity": str(wallet_ctx["total_capacity"]),
    }

    if draft.intent == "capacity":
        return CreditChatResponse(
            status="INFO",
            message=(
                f"Capacite actuelle: wallet {wallet_ctx['wallet_available']} {wallet_ctx['wallet_currency']}, "
                f"credit disponible {wallet_ctx['credit_available']} {wallet_ctx['wallet_currency']}."
            ),
            data=draft,
            summary=summary,
        )

    if draft.intent == "pending_reason":
        latest_pending = await _get_latest_pending_transfer(db, user_id)
        if not latest_pending:
            return CreditChatResponse(
                status="INFO",
                message="Je ne vois pas de demande de transfert en attente recente.",
                data=draft,
                summary=summary,
            )
        metadata = dict(getattr(latest_pending, "metadata_", {}) or {})
        reasons = metadata.get("review_reasons") or []
        if not reasons:
            reason_text = "Validation manuelle requise."
        elif "insufficient_funds" in reasons and "aml" in reasons:
            reason_text = "Le transfert attend une verification de fonds et un controle AML."
        elif "insufficient_funds" in reasons:
            reason_text = "Le transfert attend une couverture de fonds suffisante."
        elif "aml" in reasons:
            reason_text = "Le transfert attend un controle AML."
        else:
            reason_text = "Le transfert attend une validation manuelle."
        return CreditChatResponse(
            status="INFO",
            message=reason_text,
            data=draft,
            assumptions=[f"Reference analysee: {latest_pending.reference_code}."],
            summary=summary,
        )

    if draft.intent == "simulate_transfer":
        missing = []
        if draft.amount is None or draft.amount <= decimal.Decimal("0"):
            missing.append("amount")
        if not draft.currency:
            missing.append("currency")
        if missing:
            return CreditChatResponse(
                status="NEED_INFO",
                message="Je peux simuler si le montant peut passer, mais il me manque encore des informations.",
                data=draft,
                missing_fields=missing,
                suggestions=_build_suggestions(draft, missing),
                summary=summary,
            )
        is_bif = str(draft.currency or "").upper() == "BIF"
        fee_rate = await _resolve_fee_rate(db, str(draft.currency or wallet_ctx["wallet_currency"]))
        fee_amount = (decimal.Decimal(draft.amount) * fee_rate / decimal.Decimal(100)).quantize(decimal.Decimal("0.01"))
        total_required = decimal.Decimal(draft.amount) + fee_amount
        approval_capacity = wallet_ctx["credit_available"] if is_bif else wallet_ctx["total_capacity"]
        passes = total_required <= approval_capacity
        shortfall = max(decimal.Decimal("0"), total_required - approval_capacity)
        if passes:
            message_text = (
                f"Oui, {draft.amount} {draft.currency} peut passer. Total estime avec frais: {total_required} {draft.currency}."
            )
        else:
            message_text = (
                f"Non, {draft.amount} {draft.currency} ne passe pas pour l'instant. "
                f"Il manque environ {shortfall} {draft.currency}."
            )
        assumptions = [
            f"Frais estimes: {fee_amount} {draft.currency}.",
            (
                "Regle appliquee: pour BIF, seule la ligne de credit disponible compte."
                if is_bif
                else "Regle appliquee: wallet + ligne de credit disponible."
            ),
        ]
        return CreditChatResponse(
            status="INFO",
            message=message_text,
            data=draft,
            assumptions=assumptions,
            summary={
                **summary,
                "fee_rate": str(fee_rate),
                "fee_amount": str(fee_amount),
                "total_required": str(total_required),
                "approval_capacity": str(approval_capacity),
            },
        )

    return CreditChatResponse(
        status="NEED_INFO",
        message="Je peux t'aider sur la capacite, le credit disponible ou simuler si un montant peut passer.",
        data=draft,
        missing_fields=["intent"],
        suggestions=_build_suggestions(draft, ["intent"]),
        summary=summary,
    )


def cancel_credit_request() -> CreditChatResponse:
    return CreditChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)

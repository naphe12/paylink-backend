from decimal import Decimal

from sqlalchemy import cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.legacy_adapters import handle_cash_chat_with_ai
from app.cash_chat.parser import parse_cash_message
from app.cash_chat.schemas import CashChatResponse, CashDraft
from app.models.credit_lines import CreditLines
from app.models.wallet_cash_requests import WalletCashRequestStatus, WalletCashRequests
from app.models.wallets import Wallets
from app.services.assistant_suggestions import build_assistant_suggestions


SUPPORTED_CASH_PROVIDERS = {"Lumicash", "Ecocash", "eNoti", "MTN"}


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
    wallet_available = Decimal(getattr(wallet, "available", 0) or 0)
    credit_available = (
        max(Decimal(getattr(credit_line, "outstanding_amount", 0) or 0), Decimal("0"))
        if credit_line
        else Decimal("0")
    )
    pending_cash_requests = await db.scalar(
        select(func.count())
        .select_from(WalletCashRequests)
        .where(
            WalletCashRequests.user_id == user_id,
            cast(WalletCashRequests.status, String) == WalletCashRequestStatus.PENDING.value,
        )
    )
    return {
        "wallet_currency": wallet_currency,
        "wallet_available": wallet_available,
        "credit_available": credit_available,
        "total_capacity": wallet_available + credit_available,
        "pending_cash_requests": int(pending_cash_requests or 0),
    }


async def _get_latest_cash_request(db: AsyncSession, user_id):
    return await db.scalar(
        select(WalletCashRequests)
        .where(WalletCashRequests.user_id == user_id)
        .order_by(WalletCashRequests.created_at.desc())
    )


def _missing_fields_for_execution(draft: CashDraft) -> list[str]:
    missing = []
    if draft.amount is None or draft.amount <= Decimal("0"):
        missing.append("amount")
    if draft.intent == "withdraw":
        if not draft.provider_name:
            missing.append("provider_name")
        if not draft.mobile_number:
            missing.append("mobile_number")
    return missing


def _build_suggestions(draft: CashDraft, missing: list[str]) -> list[str]:
    return build_assistant_suggestions(
        "cash",
        intent=draft.intent,
        missing_fields=missing,
        extra_examples=(
            [
                "Demande un depot, un retrait ou une capacite cash.",
                "Demande le statut de ta derniere demande cash.",
            ]
            if draft.intent == "unknown"
            else None
        ),
        limit=6,
    )


async def process_cash_message(db: AsyncSession, *, user_id, message: str) -> CashChatResponse:
    from app.models.users import Users

    user_for_ai = await db.scalar(select(Users).where(Users.user_id == user_id))
    if user_for_ai is not None:
        ai_response, used_ai = await handle_cash_chat_with_ai(
            db,
            current_user=user_for_ai,
            message=message,
        )
        if used_ai:
            return ai_response

    draft = parse_cash_message(message)
    wallet_ctx = await _get_wallet_context(db, user_id)
    draft.wallet_currency = wallet_ctx["wallet_currency"]
    if not draft.currency:
        draft.currency = wallet_ctx["wallet_currency"]

    summary = {
        "wallet_currency": wallet_ctx["wallet_currency"],
        "wallet_available": str(wallet_ctx["wallet_available"]),
        "credit_available": str(wallet_ctx["credit_available"]),
        "total_capacity": str(wallet_ctx["total_capacity"]),
        "pending_cash_requests": wallet_ctx["pending_cash_requests"],
    }

    if draft.intent == "capacity":
        return CashChatResponse(
            status="INFO",
            message=(
                f"Capacite actuelle: wallet {wallet_ctx['wallet_available']} {wallet_ctx['wallet_currency']}, "
                f"credit {wallet_ctx['credit_available']} {wallet_ctx['wallet_currency']}."
            ),
            data=draft,
            executable=False,
            summary=summary,
        )

    if draft.intent == "request_status":
        latest_request = await _get_latest_cash_request(db, user_id)
        if not latest_request:
            return CashChatResponse(
                status="INFO",
                message="Je ne vois pas encore de demande cash recente sur ce compte.",
                data=draft,
                summary=summary,
            )
        request_type = str(getattr(latest_request.type, "value", latest_request.type) or "").lower()
        request_status = str(getattr(latest_request.status, "value", latest_request.status) or "").lower()
        reference_code = (getattr(latest_request, "metadata_", {}) or {}).get("reference_code")
        human_type = "depot" if request_type == "deposit" else "retrait" if request_type == "withdraw" else request_type
        message_text = f"La derniere demande cash est un {human_type} actuellement au statut {request_status}."
        assumptions = [
            f"Montant: {latest_request.amount} {latest_request.currency_code}.",
        ]
        if reference_code:
            assumptions.append(f"Reference: {reference_code}.")
        if request_status == "pending":
            assumptions.append("La demande attend encore un traitement agent ou backoffice.")
        elif request_status == "approved":
            assumptions.append("La demande a ete approuvee et attend la finalisation operationnelle.")
        elif request_status == "completed":
            assumptions.append("La demande a deja ete finalisee.")
        elif request_status == "rejected":
            assumptions.append("La demande a ete rejetee. Verifie les details ou recree une nouvelle demande si besoin.")
        elif request_status == "cancelled":
            assumptions.append("La demande a ete annulee. Il faut en creer une nouvelle si l'operation est toujours souhaitee.")
        return CashChatResponse(
            status="INFO",
            message=message_text,
            data=draft,
            assumptions=assumptions,
            summary={
                **summary,
                "latest_request_status": request_status,
                "latest_request_type": human_type,
                "latest_request_amount": str(latest_request.amount),
                "latest_request_currency": str(latest_request.currency_code),
            },
        )

    if draft.intent == "unknown":
        return CashChatResponse(
            status="NEED_INFO",
            message="Je peux aider pour un depot, un retrait ou une demande de capacite cash.",
            data=draft,
            missing_fields=["intent"],
            executable=False,
            suggestions=_build_suggestions(draft, ["intent"]),
            summary=summary,
        )

    missing = _missing_fields_for_execution(draft)
    if draft.intent == "withdraw" and draft.provider_name and str(draft.provider_name) not in SUPPORTED_CASH_PROVIDERS:
        missing = ["provider_name", *[item for item in missing if item != "provider_name"]]

    executable = not missing
    action_label = "depot" if draft.intent == "deposit" else "retrait"
    message_text = (
        f"Je suis pret a preparer la demande de {action_label} de {draft.amount} {draft.currency}."
        if executable
        else f"Je peux preparer la demande de {action_label}, mais il manque encore des informations."
    )
    return CashChatResponse(
        status="CONFIRM" if executable else "NEED_INFO",
        message=message_text,
        data=draft,
        missing_fields=missing,
        executable=executable,
        suggestions=_build_suggestions(draft, missing),
        summary=summary,
    )


def cancel_cash_request() -> CashChatResponse:
    return CashChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)

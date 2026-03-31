import decimal

from sqlalchemy import String, cast, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.legacy_adapters import handle_wallet_support_with_ai
from app.models.client_balance_events import ClientBalanceEvents
from app.models.external_transfers import ExternalTransfers
from app.models.users import Users
from app.models.wallet_cash_requests import WalletCashRequests
from app.models.wallet_transactions import WalletTransactions
from app.models.wallets import Wallets
from app.services.assistant_suggestions import build_assistant_suggestions
from app.wallet_support_chat.parser import parse_wallet_support_message
from app.wallet_support_chat.schemas import WalletSupportChatResponse


def _build_suggestions() -> list[str]:
    return build_assistant_suggestions("wallet_support")


async def _load_context(db: AsyncSession, user_id):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user_id))
    latest_wallet_tx = await db.scalar(
        select(WalletTransactions)
        .where(WalletTransactions.user_id == user_id)
        .order_by(desc(WalletTransactions.created_at))
    )
    latest_debit_tx = await db.scalar(
        select(WalletTransactions)
        .where(
            WalletTransactions.user_id == user_id,
            cast(WalletTransactions.direction, String).in_(("debit", "DEBIT")),
        )
        .order_by(desc(WalletTransactions.created_at))
    )
    latest_balance_event = await db.scalar(
        select(ClientBalanceEvents)
        .where(ClientBalanceEvents.user_id == user_id)
        .order_by(desc(ClientBalanceEvents.occurred_at))
    )
    latest_cash_request = await db.scalar(
        select(WalletCashRequests)
        .where(WalletCashRequests.user_id == user_id)
        .order_by(desc(WalletCashRequests.created_at))
    )
    latest_external_transfer = await db.scalar(
        select(ExternalTransfers)
        .where(ExternalTransfers.user_id == user_id)
        .order_by(desc(ExternalTransfers.created_at))
    )
    summary = {
        "wallet_currency": str(getattr(wallet, "currency_code", "") or "EUR").upper(),
        "wallet_available": str(decimal.Decimal(getattr(wallet, "available", 0) or 0)),
        "wallet_pending": str(decimal.Decimal(getattr(wallet, "pending", 0) or 0)),
        "account_status": str(getattr(user, "status", "") or ""),
        "kyc_status": str(getattr(user, "kyc_status", "") or ""),
        "daily_limit": str(decimal.Decimal(getattr(user, "daily_limit", 0) or 0)),
        "used_daily": str(decimal.Decimal(getattr(user, "used_daily", 0) or 0)),
        "monthly_limit": str(decimal.Decimal(getattr(user, "monthly_limit", 0) or 0)),
        "used_monthly": str(decimal.Decimal(getattr(user, "used_monthly", 0) or 0)),
    }
    return user, wallet, latest_wallet_tx, latest_debit_tx, latest_balance_event, latest_cash_request, latest_external_transfer, summary


async def process_wallet_support_message(db: AsyncSession, *, user_id, message: str) -> WalletSupportChatResponse:
    user_for_ai = await db.scalar(select(Users).where(Users.user_id == user_id))
    if user_for_ai is not None:
        ai_response, used_ai = await handle_wallet_support_with_ai(
            db,
            current_user=user_for_ai,
            message=message,
        )
        if used_ai:
            return ai_response

    draft = parse_wallet_support_message(message)
    (
        user,
        wallet,
        latest_wallet_tx,
        latest_debit_tx,
        latest_balance_event,
        latest_cash_request,
        latest_external_transfer,
        summary,
    ) = await _load_context(db, user_id)

    if not user or not wallet:
        return WalletSupportChatResponse(status="ERROR", message="Impossible de charger le dossier wallet.", data=draft)

    if draft.intent == "balance_drop":
        if latest_debit_tx:
            return WalletSupportChatResponse(
                status="INFO",
                message=(
                    f"La derniere sortie detectee est un debit de {latest_debit_tx.amount} {latest_debit_tx.currency_code} "
                    f"sur {latest_debit_tx.operation_type}."
                ),
                data=draft,
                assumptions=[
                    str(getattr(latest_debit_tx, "description", "") or "Aucune description detaillee."),
                ],
                summary=summary,
            )
        if latest_balance_event:
            return WalletSupportChatResponse(
                status="INFO",
                message="Le dernier evenement de balance montre une variation recente du solde.",
                data=draft,
                assumptions=[
                    f"Variation: {latest_balance_event.amount_delta} {latest_balance_event.currency}.",
                    f"Source: {latest_balance_event.source}.",
                ],
                summary=summary,
            )

    if draft.intent == "missing_deposit":
        if latest_cash_request and str(getattr(latest_cash_request.type, 'value', latest_cash_request.type) or '').lower() == "deposit":
            status = str(getattr(latest_cash_request.status, "value", latest_cash_request.status) or "").lower()
            message_text = (
                "Je vois une derniere demande de depot encore en attente."
                if status == "pending"
                else f"Je vois une derniere demande de depot au statut {status}."
            )
            return WalletSupportChatResponse(
                status="INFO",
                message=message_text,
                data=draft,
                assumptions=[
                    f"Montant: {latest_cash_request.amount} {latest_cash_request.currency_code}.",
                    "Si le depot n'apparait pas encore, il est probablement encore en cours de traitement."
                    if status == "pending"
                    else "Verifie la demande cash liee pour plus de details.",
                ],
                summary=summary,
            )
        return WalletSupportChatResponse(
            status="INFO",
            message="Je ne vois pas de depot cash recent en attente dans le dossier.",
            data=draft,
            assumptions=["Verifie si le mouvement attendu etait un cash-in, un virement ou un autre type d'entree."],
            summary=summary,
        )

    if draft.intent == "blocked_withdraw":
        assumptions: list[str] = []
        if str(getattr(user, "status", "") or "").lower() == "frozen":
            assumptions.append("Le compte est actuellement gele.")
        if decimal.Decimal(getattr(user, "used_daily", 0) or 0) >= decimal.Decimal(getattr(user, "daily_limit", 0) or 0):
            assumptions.append("La limite journaliere est atteinte.")
        if decimal.Decimal(getattr(user, "used_monthly", 0) or 0) >= decimal.Decimal(getattr(user, "monthly_limit", 0) or 0):
            assumptions.append("La limite mensuelle est atteinte.")
        if latest_cash_request and str(getattr(latest_cash_request.type, 'value', latest_cash_request.type) or '').lower() == "withdraw":
            assumptions.append(f"Derniere demande de retrait: {latest_cash_request.status}.")
        if not assumptions:
            assumptions.append("Le blocage peut venir du solde disponible, d'un traitement agent ou d'un controle manuel.")
        return WalletSupportChatResponse(
            status="INFO",
            message="Le retrait semble bloque par une contrainte de compte, de limite ou de traitement en attente.",
            data=draft,
            assumptions=assumptions,
            summary=summary,
        )

    if draft.intent == "frozen_account":
        return WalletSupportChatResponse(
            status="INFO",
            message=f"Statut du compte: {summary['account_status']}. KYC actuel: {summary['kyc_status']}.",
            data=draft,
            assumptions=[
                "Un compte gele ou suspendu bloque certaines operations wallet et transfert."
                if summary["account_status"] in {"frozen", "suspended"}
                else "Je ne vois pas de gel explicite dans le statut actuel.",
            ],
            summary=summary,
        )

    if draft.intent == "cant_send":
        assumptions: list[str] = []
        if summary["account_status"] in {"frozen", "suspended"}:
            assumptions.append("Le statut du compte bloque l'envoi.")
        if decimal.Decimal(summary["used_daily"]) >= decimal.Decimal(summary["daily_limit"]):
            assumptions.append("La limite journaliere est atteinte.")
        if decimal.Decimal(summary["used_monthly"]) >= decimal.Decimal(summary["monthly_limit"]):
            assumptions.append("La limite mensuelle est atteinte.")
        if latest_external_transfer and str(getattr(latest_external_transfer, "status", "") or "").lower() in {"pending", "initiated"}:
            assumptions.append(f"Derniere demande de transfert encore {latest_external_transfer.status}.")
        if not assumptions:
            assumptions.append("L'envoi peut etre bloque par le solde, une revue manuelle ou une limite contextuelle.")
        return WalletSupportChatResponse(
            status="INFO",
            message="Je vois plusieurs causes possibles qui peuvent bloquer l'envoi actuellement.",
            data=draft,
            assumptions=assumptions,
            summary=summary,
        )

    if draft.intent == "latest_movement":
        if latest_wallet_tx:
            return WalletSupportChatResponse(
                status="INFO",
                message=(
                    f"Dernier mouvement wallet: {latest_wallet_tx.direction} {latest_wallet_tx.amount} "
                    f"{latest_wallet_tx.currency_code} sur {latest_wallet_tx.operation_type}."
                ),
                data=draft,
                assumptions=[str(getattr(latest_wallet_tx, "description", "") or "Aucune description detaillee.")],
                summary=summary,
            )
        return WalletSupportChatResponse(
            status="INFO",
            message="Je ne vois pas encore de mouvement wallet recent.",
            data=draft,
            summary=summary,
        )

    return WalletSupportChatResponse(
        status="NEED_INFO",
        message="Je peux aider sur un solde qui baisse, un depot non visible, un retrait bloque, un compte gele ou un envoi impossible.",
        data=draft,
        suggestions=_build_suggestions(),
        summary=summary,
    )


def cancel_wallet_support_request() -> WalletSupportChatResponse:
    return WalletSupportChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)

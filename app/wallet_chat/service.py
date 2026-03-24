import decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_lines import CreditLines
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions
from app.models.wallets import Wallets
from app.wallet_chat.parser import parse_wallet_message
from app.wallet_chat.schemas import WalletChatResponse


def _build_suggestions() -> list[str]:
    return [
        "Demande ton solde wallet.",
        "Demande tes limites journalieres et mensuelles.",
        "Demande les derniers mouvements.",
        "Demande le statut de ton compte.",
    ]


async def _get_wallet_context(db: AsyncSession, user_id):
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == user_id))
    credit_line = await db.scalar(
        select(CreditLines)
        .where(CreditLines.user_id == user_id, CreditLines.deleted_at.is_(None))
        .order_by(CreditLines.created_at.desc())
    )
    recent_movements = (
        await db.execute(
            select(WalletTransactions)
            .where(WalletTransactions.user_id == user_id)
            .order_by(desc(WalletTransactions.created_at))
            .limit(5)
        )
    ).scalars().all()
    wallet_currency = str(getattr(wallet, "currency_code", "") or "").upper() or "EUR"
    wallet_available = decimal.Decimal(getattr(wallet, "available", 0) or 0)
    credit_available = (
        max(decimal.Decimal(getattr(credit_line, "outstanding_amount", 0) or 0), decimal.Decimal("0"))
        if credit_line
        else decimal.Decimal("0")
    )
    return user, wallet, {
        "wallet_currency": wallet_currency,
        "wallet_available": wallet_available,
        "wallet_pending": decimal.Decimal(getattr(wallet, "pending", 0) or 0),
        "bonus_balance": decimal.Decimal(getattr(wallet, "bonus_balance", 0) or 0),
        "credit_available": credit_available,
        "total_capacity": wallet_available + credit_available,
        "daily_limit": decimal.Decimal(getattr(user, "daily_limit", 0) or 0),
        "used_daily": decimal.Decimal(getattr(user, "used_daily", 0) or 0),
        "monthly_limit": decimal.Decimal(getattr(user, "monthly_limit", 0) or 0),
        "used_monthly": decimal.Decimal(getattr(user, "used_monthly", 0) or 0),
        "account_status": str(getattr(user, "status", "") or ""),
        "kyc_status": str(getattr(user, "kyc_status", "") or ""),
        "recent_movements": [
            {
                "direction": str(getattr(item, "direction", "") or ""),
                "amount": str(getattr(item, "amount", "") or ""),
                "currency_code": str(getattr(item, "currency_code", "") or wallet_currency),
                "operation_type": str(getattr(item, "operation_type", "") or ""),
                "description": str(getattr(item, "description", "") or ""),
                "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
            }
            for item in recent_movements
        ],
    }


async def process_wallet_message(db: AsyncSession, *, user_id, message: str) -> WalletChatResponse:
    draft = parse_wallet_message(message)
    user, wallet, summary = await _get_wallet_context(db, user_id)
    if not user or not wallet:
        return WalletChatResponse(status="ERROR", message="Impossible de charger la situation wallet.", data=draft)

    if draft.intent == "balance":
        return WalletChatResponse(
            status="INFO",
            message=(
                f"Solde wallet: {summary['wallet_available']} {summary['wallet_currency']}. "
                f"En attente: {summary['wallet_pending']} {summary['wallet_currency']}. "
                f"Bonus: {summary['bonus_balance']} {summary['wallet_currency']}."
            ),
            data=draft,
            summary=summary,
        )

    if draft.intent == "limits":
        return WalletChatResponse(
            status="INFO",
            message=(
                f"Limite journaliere: {summary['used_daily']} / {summary['daily_limit']} {summary['wallet_currency']}. "
                f"Limite mensuelle: {summary['used_monthly']} / {summary['monthly_limit']} {summary['wallet_currency']}."
            ),
            data=draft,
            summary=summary,
        )

    if draft.intent == "recent_activity":
        recent_movements = summary["recent_movements"]
        if not recent_movements:
            return WalletChatResponse(
                status="INFO",
                message="Je ne vois pas encore de mouvement wallet recent.",
                data=draft,
                summary=summary,
            )
        latest = recent_movements[0]
        assumptions = [
            f"{item['direction']} {item['amount']} {item['currency_code']} - {item['operation_type']}"
            for item in recent_movements[:3]
        ]
        return WalletChatResponse(
            status="INFO",
            message=(
                f"Dernier mouvement: {latest['direction']} {latest['amount']} {latest['currency_code']} "
                f"sur {latest['operation_type']}."
            ),
            data=draft,
            assumptions=assumptions,
            summary=summary,
        )

    if draft.intent == "account_status":
        return WalletChatResponse(
            status="INFO",
            message=(
                f"Statut du compte: {summary['account_status']}. "
                f"KYC: {summary['kyc_status']}. "
                f"Capacite totale actuelle: {summary['total_capacity']} {summary['wallet_currency']}."
            ),
            data=draft,
            summary=summary,
        )

    return WalletChatResponse(
        status="NEED_INFO",
        message="Je peux t'aider sur le solde wallet, les limites, les mouvements recents ou le statut du compte.",
        data=draft,
        suggestions=_build_suggestions(),
        summary=summary,
    )


def cancel_wallet_request() -> WalletChatResponse:
    return WalletChatResponse(status="CANCELLED", message="Operation annulee.", executable=False)

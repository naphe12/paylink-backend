from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.countries import Countries
from app.models.user_currency_preferences import UserCurrencyPreferences
from app.models.users import Users
from app.models.wallets import Wallets
from app.routers.ref.exchange import _resolve_exchange_rate
from app.services.wallet_service import get_crypto_balance

SUPPORTED_DISPLAY_CURRENCIES = {"BIF", "EUR", "USD", "USDC", "USDT"}


def _normalize_currency_code(value: str | None, fallback: str = "EUR") -> str:
    raw = str(value or fallback or "").strip().upper()
    return (raw[:5] or fallback).upper()


async def _get_primary_wallet(db: AsyncSession, user_id):
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    return await db.scalar(
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
    )


async def _get_country_currency(db: AsyncSession, country_code: str | None) -> str | None:
    if not country_code:
        return None
    return await db.scalar(
        select(Countries.currency_code).where(Countries.country_code == country_code)
    )


async def get_user_display_currency_preference(
    db: AsyncSession,
    *,
    user: Users,
) -> dict:
    preference = await db.get(UserCurrencyPreferences, user.user_id)
    primary_wallet = await _get_primary_wallet(db, user.user_id)
    wallet_currency = _normalize_currency_code(getattr(primary_wallet, "currency_code", None), "EUR")
    country_currency = _normalize_currency_code(
        await _get_country_currency(db, getattr(user, "country_code", None)),
        wallet_currency,
    )

    available_currencies = sorted(
        {
            wallet_currency,
            country_currency,
            "USD",
            "USDC",
            "USDT",
            "BIF",
            "EUR",
        }
    )

    if preference and preference.display_currency:
        display_currency = _normalize_currency_code(preference.display_currency, country_currency)
        source = "user_preference"
    elif country_currency:
        display_currency = country_currency
        source = "country_default"
    else:
        display_currency = wallet_currency
        source = "wallet_default"

    if display_currency not in SUPPORTED_DISPLAY_CURRENCIES:
        display_currency = wallet_currency if wallet_currency in SUPPORTED_DISPLAY_CURRENCIES else "EUR"
        source = "wallet_default"

    return {
        "display_currency": display_currency,
        "source": source,
        "available_currencies": [code for code in available_currencies if code in SUPPORTED_DISPLAY_CURRENCIES],
    }


async def set_user_display_currency_preference(
    db: AsyncSession,
    *,
    user: Users,
    display_currency: str,
) -> dict:
    normalized = _normalize_currency_code(display_currency)
    if normalized not in SUPPORTED_DISPLAY_CURRENCIES:
        raise ValueError("Display currency not supported")

    preference = await db.get(UserCurrencyPreferences, user.user_id)
    if preference is None:
        preference = UserCurrencyPreferences(
            user_id=user.user_id,
            display_currency=normalized,
        )
        db.add(preference)
    else:
        preference.display_currency = normalized
        preference.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return await get_user_display_currency_preference(db, user=user)


async def _resolve_rate_to_display_currency(
    db: AsyncSession,
    *,
    origin_currency: str,
    display_currency: str,
) -> tuple[Decimal | None, str | None]:
    if origin_currency == display_currency:
        return Decimal("1"), "identity"

    rate, source = await _resolve_exchange_rate(db, origin_currency, display_currency)
    if rate is None:
        return None, source
    return Decimal(str(rate)), source


async def get_wallet_display_summary(
    db: AsyncSession,
    *,
    user: Users,
) -> dict:
    preference = await get_user_display_currency_preference(db, user=user)
    display_currency = preference["display_currency"]
    primary_wallet = await _get_primary_wallet(db, user.user_id)

    balances = []
    if primary_wallet is not None:
        balances.append(
            {
                "currency_code": _normalize_currency_code(primary_wallet.currency_code),
                "available": Decimal(str(primary_wallet.available or 0)),
                "pending": Decimal(str(primary_wallet.pending or 0)),
            }
        )

    for token in ("USDC", "USDT"):
        balance = await get_crypto_balance(str(user.user_id), token, db=db)
        balances.append(
            {
                "currency_code": token,
                "available": Decimal(str(balance or 0)),
                "pending": Decimal("0"),
            }
        )

    total_available = Decimal("0")
    total_pending = Decimal("0")
    has_available_estimate = False
    has_pending_estimate = False

    for item in balances:
        rate, source = await _resolve_rate_to_display_currency(
            db,
            origin_currency=item["currency_code"],
            display_currency=display_currency,
        )
        item["rate_to_display_currency"] = rate
        item["rate_source"] = source
        if rate is None:
            item["estimated_display_available"] = None
            item["estimated_display_pending"] = None
            continue

        item["estimated_display_available"] = (item["available"] * rate).quantize(Decimal("0.000001"))
        item["estimated_display_pending"] = (item["pending"] * rate).quantize(Decimal("0.000001"))
        total_available += item["estimated_display_available"]
        total_pending += item["estimated_display_pending"]
        has_available_estimate = True
        has_pending_estimate = True

    return {
        "display_currency": display_currency,
        "source": preference["source"],
        "available_currencies": preference["available_currencies"],
        "estimated_total_available": total_available if has_available_estimate else None,
        "estimated_total_pending": total_pending if has_pending_estimate else None,
        "balances": balances,
        "generated_at": datetime.now(timezone.utc),
    }

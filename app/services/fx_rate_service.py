from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_latest_active_custom_rate(
    db: AsyncSession,
    *,
    origin: str,
    destination: str,
) -> Decimal | None:
    res = await db.execute(
        text(
            """
            SELECT rate
            FROM paylink.fx_custom_rates
            WHERE origin_currency = :origin
              AND destination_currency = :destination
              AND is_active = TRUE
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """
        ),
        {
            "origin": str(origin or "").upper(),
            "destination": str(destination or "").upper(),
        },
    )
    row = res.first()
    if not row or row[0] is None:
        return None

    rate = Decimal(str(row[0]))
    if rate <= 0:
        return None
    return rate


async def resolve_stablecoin_bif_rate(
    db: AsyncSession,
    *,
    stablecoin: str,
    override_rate: Decimal | None = None,
    stablecoin_usd_rate: Decimal | None = None,
    default_rate: Decimal | None = None,
) -> Decimal:
    if override_rate is not None:
        rate = Decimal(str(override_rate))
        if rate <= 0:
            raise ValueError("Rate must be > 0")
        return rate

    normalized_stablecoin = str(stablecoin or "").upper()
    direct_rate = await get_latest_active_custom_rate(
        db,
        origin=normalized_stablecoin,
        destination="BIF",
    )
    usd_bif_rate = await get_latest_active_custom_rate(
        db,
        origin="USD",
        destination="BIF",
    )

    if usd_bif_rate is None:
        if direct_rate is not None:
            return direct_rate
        if default_rate is not None:
            return Decimal(str(default_rate))
        raise ValueError("USD/BIF rate not configured")

    if normalized_stablecoin == "USD":
        effective_stablecoin_usd_rate = Decimal("1")
    elif stablecoin_usd_rate is not None:
        effective_stablecoin_usd_rate = Decimal(str(stablecoin_usd_rate))
    else:
        direct_stablecoin_usd_rate = await get_latest_active_custom_rate(
            db,
            origin=normalized_stablecoin,
            destination="USD",
        )
        if direct_stablecoin_usd_rate is not None:
            effective_stablecoin_usd_rate = direct_stablecoin_usd_rate
        else:
            inverse_usd_stablecoin_rate = await get_latest_active_custom_rate(
                db,
                origin="USD",
                destination=normalized_stablecoin,
            )
            if inverse_usd_stablecoin_rate is not None:
                effective_stablecoin_usd_rate = Decimal("1") / inverse_usd_stablecoin_rate
            else:
                effective_stablecoin_usd_rate = Decimal("1")

    if effective_stablecoin_usd_rate <= 0:
        raise ValueError("Stablecoin/USD rate must be > 0")

    return (effective_stablecoin_usd_rate * usd_bif_rate).quantize(Decimal("0.00000001"))

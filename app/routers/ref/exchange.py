from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.fxconversions import FxConversions
from app.models.fx_custom_rates import FxCustomRates
from app.models.general_settings import GeneralSettings
from app.services.fx_provider import get_open_exchange_rate_to_eur

router = APIRouter(prefix="/api/exchange-rate", tags=["exchange"])

FEE_RULES = {
    "BIF": 6.5,
    "RWF": 6.0,
    "CDF": 5.0,
    "KES": 6.8,
}


async def _resolve_fee_percent(db: AsyncSession, destination: str) -> float:
    settings_row = await db.scalar(
        select(GeneralSettings).order_by(GeneralSettings.created_at.desc())
    )
    if settings_row and getattr(settings_row, "charge", None) is not None:
        return float(settings_row.charge)
    return float(FEE_RULES.get(destination, 2.5))


def _normalize_currency_code(value: str | None, fallback: str | None = None) -> str:
    raw = str(value or fallback or "").strip().upper()
    return raw[:3]


async def _get_custom_rate(
    db: AsyncSession, origin: str, destination: str
) -> FxCustomRates | None:
    result = await db.execute(
        select(FxCustomRates).where(
            FxCustomRates.origin_currency == origin,
            FxCustomRates.destination_currency == destination,
            FxCustomRates.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _get_internal_rate(db: AsyncSession, origin: str, destination: str) -> tuple[float | None, str]:
    if origin == destination:
        return 1.0, "identity"

    custom = await _get_custom_rate(db, origin, destination)
    if custom and custom.rate is not None:
        return float(custom.rate), str(custom.source or "custom_rate")

    fx_row = await db.scalar(
        select(FxConversions.rate_used)
        .where(
            FxConversions.from_currency == origin,
            FxConversions.to_currency == destination,
        )
        .order_by(FxConversions.created_at.desc())
        .limit(1)
    )
    if fx_row not in (None, 0):
        return float(fx_row), "internal_fx_conversion"

    return None, "internal_rate_unavailable"


async def _get_official_rate(origin: str, destination: str) -> tuple[float | None, str]:
    if destination == "EUR":
        rate = await get_open_exchange_rate_to_eur(origin)
        if rate:
            return rate, "openexchangerates_to_eur"
        return None, "openexchangerates_to_eur_unavailable"
    return None, "official_rate_unavailable"


async def _resolve_exchange_rate(
    db: AsyncSession, origin: str, destination: str
) -> tuple[float | None, str]:
    if origin == destination:
        return 1.0, "identity"

    if destination == "EUR" and origin != "EUR":
        official_rate, official_source = await _get_official_rate(origin, "EUR")
        if official_rate:
            return official_rate, official_source
        return None, "missing_source_eur_webservice_rate"

    if destination == "BIF" and origin != "EUR":
        source_to_eur, source_to_eur_source = await _get_official_rate(origin, "EUR")
        eur_to_bif, eur_to_bif_source = await _get_internal_rate(db, "EUR", "BIF")
        if source_to_eur and eur_to_bif:
            return source_to_eur * eur_to_bif, f"{source_to_eur_source}_via_eur_{eur_to_bif_source}"
        return None, "missing_source_eur_or_eur_bif_rate"

    internal_rate, internal_source = await _get_internal_rate(db, origin, destination)
    if internal_rate:
        return internal_rate, internal_source

    official_rate, official_source = await _get_official_rate(origin, destination)
    if official_rate:
        return official_rate, official_source

    if origin != "EUR" and destination != "EUR":
        origin_to_eur, origin_to_eur_source = await _resolve_exchange_rate(db, origin, "EUR")
        eur_to_destination, eur_to_destination_source = await _resolve_exchange_rate(
            db, "EUR", destination
        )
        if origin_to_eur and eur_to_destination:
            return (
                origin_to_eur * eur_to_destination,
                f"{origin_to_eur_source}_via_eur_{eur_to_destination_source}",
            )

    return None, "unsupported_currency_pair"


@router.get("/")
async def get_exchange_rate(
    origin: str = Query("EUR"),
    destination: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    origin = _normalize_currency_code(origin, "EUR")
    destination = _normalize_currency_code(destination)
    if not origin or not destination:
        raise HTTPException(status_code=400, detail="Devise invalide")

    fee_percent = await _resolve_fee_percent(db, destination)
    rate, source = await _resolve_exchange_rate(db, origin, destination)
    if rate is None:
        raise HTTPException(
            status_code=400,
            detail=f"Devise non supportee pour la paire {origin}/{destination}",
        )

    return {
        "origin": origin,
        "destination": destination,
        "rate": round(rate, 8 if rate < 1 else 2),
        "fees_percent": fee_percent,
        "source": source,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/custom", response_model=list[dict])
async def list_custom_rates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FxCustomRates))
    rows = result.scalars().all()
    return [
        {
            "destination_currency": r.destination_currency,
            "rate": float(r.rate),
            "source": r.source,
            "is_active": r.is_active,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.put("/{currency_code}")
async def update_custom_rate(
    currency_code: str, new_rate: float, db: AsyncSession = Depends(get_db)
):
    currency_code = _normalize_currency_code(currency_code)
    result = await db.execute(
        select(FxCustomRates).where(FxCustomRates.destination_currency == currency_code)
    )
    fx = result.scalar_one_or_none()

    if fx:
        await db.execute(
            update(FxCustomRates)
            .where(FxCustomRates.destination_currency == currency_code)
            .values(rate=new_rate, updated_at=datetime.utcnow())
        )
    else:
        await db.execute(
            insert(FxCustomRates).values(destination_currency=currency_code, rate=new_rate)
        )
    await db.commit()
    return {"message": f"Taux mis a jour pour {currency_code}", "rate": new_rate}

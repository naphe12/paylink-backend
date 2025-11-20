from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.fx_custom_rates import FxCustomRates

router = APIRouter(prefix="/api/exchange-rate", tags=["exchange"])

# 🔹 Frais selon zone
FEE_RULES = {
    "BIF": 6.5,
    "RWF": 6.0,
    "CDF": 5.0,
    "KES": 6.8,
}

@router.get("/")
async def get_exchange_rate(
    origin: str = Query("EUR"),
    destination: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    🔹 Vérifie si un taux est défini dans la base (marché parallèle ou custom)
    🔹 Sinon, récupère le taux officiel via exchangerate.host
    """
    result = await db.execute(
        select(FxCustomRates).where(
            FxCustomRates.origin_currency == origin,
            FxCustomRates.destination_currency == destination,
            FxCustomRates.is_active.is_(True)
        )
    )
    custom = result.scalar_one_or_none()

    # 1️⃣ Taux interne (prioritaire)
    if custom:
        return {
            "origin": origin,
            "destination": destination,
            "rate": float(custom.rate),
            "fees_percent": FEE_RULES.get(destination, 2.5),
            "source": custom.source,
            "timestamp": custom.updated_at.isoformat() if custom.updated_at else None
        }

    # 2️⃣ Sinon API publique
    url = f"https://api.exchangerate.host/convert?from={origin}&to={destination}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail="Erreur API ExchangeRate")
        data = res.json()

    if not data.get("info"):
        raise HTTPException(status_code=400, detail="Devise non supportée")

    rate = data["info"]["rate"]
    fee = FEE_RULES.get(destination, 2.5)

    return {
        "origin": origin,
        "destination": destination,
        "rate": round(rate, 2),
        "fees_percent": fee,
        "source": "official_rate",
        "timestamp": datetime.utcnow().isoformat()
    }

# ==========================================================
# 👨‍💼 Administration des taux
# ==========================================================

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
            "updated_at": r.updated_at
        } for r in rows
    ]

@router.put("/{currency_code}")
async def update_custom_rate(currency_code: str, new_rate: float, db: AsyncSession = Depends(get_db)):
    """
    🔹 Met à jour ou crée un taux personnalisé
    """
    result = await db.execute(select(FxCustomRates).where(FxCustomRates.destination_currency == currency_code))
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
    return {"message": f"Taux mis à jour pour {currency_code}", "rate": new_rate}

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.general_settings import GeneralSettings
from app.models.fx_custom_rates import FxCustomRates

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])


@router.get("/general")
async def get_general_settings(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await db.scalar(
        select(GeneralSettings).order_by(GeneralSettings.created_at.desc())
    )
    if not row:
        raise HTTPException(status_code=404, detail="General settings not found")
    return {
        "charge": float(row.charge),
        "fix_charge": float(row.fix_charge),
        "coefficient": float(row.coefficient),
        "smsTransfert_fees": float(row.smsTransfert_fees),
        "currency": row.currency,
        "updated_at": row.updated_at,
    }


@router.put("/general")
async def update_general_settings(
    charge: Optional[float] = None,
    fix_charge: Optional[float] = None,
    coefficient: Optional[float] = None,
    smsTransfert_fees: Optional[float] = None,
    currency: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await db.scalar(
        select(GeneralSettings).order_by(GeneralSettings.created_at.desc())
    )
    if row:
        stmt = (
            update(GeneralSettings)
            .where(GeneralSettings.id == row.id)
            .values(
                {
                    **(
                        {"charge": charge}
                        if charge is not None
                        else {}
                    ),
                    **(
                        {"fix_charge": fix_charge}
                        if fix_charge is not None
                        else {}
                    ),
                    **(
                        {"coefficient": coefficient}
                        if coefficient is not None
                        else {}
                    ),
                    **(
                        {"smsTransfert_fees": smsTransfert_fees}
                        if smsTransfert_fees is not None
                        else {}
                    ),
                    **({"currency": currency} if currency else {}),
                    "updated_at": datetime.utcnow(),
                }
            )
        )
        await db.execute(stmt)
    else:
        await db.execute(
            insert(GeneralSettings).values(
                charge=charge or 0,
                fix_charge=fix_charge or 0,
                coefficient=coefficient or 1,
                smsTransfert_fees=smsTransfert_fees or 0,
                currency=currency or "EUR",
                amount=0,
                bonus=0,
                sms_notification=1,
                email_notification=1,
                decimal_after_point=2,
                fixValue=0,
                smsPhone="",
                account="",
                account_name="",
            )
        )
    await db.commit()
    return {"message": "General settings updated"}


@router.get("/fx-custom")
async def list_fx_custom_rates(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    rows = (
        await db.execute(select(FxCustomRates))
    ).scalars().all()
    return [
        {
            "destination_currency": r.destination_currency,
            "origin_currency": r.origin_currency,
            "rate": float(r.rate),
            "is_active": r.is_active,
            "source": r.source,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.put("/fx-custom/{currency}")
async def update_fx_custom_rate(
    currency: str,
    new_rate: float,
    is_active: Optional[bool] = None,
    origin: str = "EUR",
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await db.scalar(
        select(FxCustomRates).where(
            FxCustomRates.destination_currency == currency
        )
    )
    if row:
        await db.execute(
            update(FxCustomRates)
            .where(FxCustomRates.destination_currency == currency)
            .values(
                rate=new_rate,
                is_active=is_active
                if is_active is not None
                else row.is_active,
                updated_at=datetime.utcnow(),
            )
        )
    else:
        await db.execute(
            insert(FxCustomRates).values(
                origin_currency=origin,
                destination_currency=currency,
                rate=new_rate,
                is_active=is_active if is_active is not None else True,
                updated_at=datetime.utcnow(),
            )
        )
    await db.commit()
    return {"message": f"Taux mis à jour pour {currency}", "rate": new_rate}

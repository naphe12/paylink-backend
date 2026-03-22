from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Countries

router = APIRouter()

# @router.get("/countries", response_model=list[CountryRead])
# def list_countries(db: Session = Depends(get_db)):
#     return db.query(Country).order_by(Country.name).all()

@router.get("/")
async def list_countries(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Countries).order_by(Countries.name.asc()))
    countries = result.scalars().all()
    return [
        {
            "country_code": c.country_code,
            "name": c.name,
            "currency_code": c.currency_code,
            "phone_prefix": c.phone_prefix,
        }
        for c in countries
    ]

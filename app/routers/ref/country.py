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
    result = await db.execute(select(Countries))
    countries = result.scalars().all()  # Récupère les objets Country
    print("✅ Pays récupérés :", len(countries))
    return [{"country_code": c.country_code, "name": c.name} for c in countries]
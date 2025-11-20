from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.tontinecontributions import TontineContributions
from app.models.tontinemembers import TontineMembers
from app.models.tontines import Tontines
from app.models.users import Users
from app.services.mobilemoney.lumicash import send_lumicash_payment

router = APIRouter()
@router.get("/users/search")
async def search_users(query: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Users.user_id, Users.full_name, Users.phone_e164, Users.paytag)\
        .where(
            or_(
                Users.phone.ilike(f"%{query}%"),
                Users.paytag.ilike(f"%{query}%"),
                Users.name.ilike(f"%{query}%")
            )
        ).limit(10)

    result = await db.execute(stmt)
    users = [{"id": r[0], "name": r[1], "phone": r[2], "paytag": r[3]} for r in result.all()]
    return users

@router.post("/tontines/{tontine_id}/members/add")
async def add_member(tontine_id: str, user_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):

    exists = await db.scalar(
        select(TontineMembers).where(
            TontineMembers.tontine_id == tontine_id,
            TontineMembers.user_id == user_id
        )
    )
    if exists:
        raise HTTPException(400, "Cet utilisateur est déjà membre.")

    new_member = TontineMembers(tontine_id=tontine_id, user_id=user_id)
    db.add(new_member)
    await db.commit()
    return {"message": "✅ Membre ajouté avec succès"}

@router.post("/tontines/{tontine_id}/contribute/mobilemoney")
async def contribute_mobilemoney(tontine_id: str, db: AsyncSession = Depends(get_db), current_user: Users = Depends(get_current_user)):

    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    # 1) Créer une contribution en attente
    contrib = TontineContributions(
        tontine_id=tontine_id,
        user_id=current_user.user_id,
        amount=tontine.amount_per_member,
        status="pending"
    )
    db.add(contrib)
    await db.flush()

    # 2) Appel API Mobile Money → (exemple Lumicash)
    await send_lumicash_payment(
        phone=current_user.phone,
        amount=float(tontine.amount_per_member),
        reference=str(contrib.contribution_id)
    )

    await db.commit()
    return {"message": "Paiement en attente de confirmation", "contribution_id": str(contrib.contribution_id)}



from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.dependencies.auth import get_current_user_db
from app.models.user_auth import UserAuth
from app.models.users import Users

router = APIRouter(prefix="/auth", tags=["Auth"])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    auth_entry = await db.scalar(select(UserAuth).where(UserAuth.user_id == current_user.user_id))
    if not auth_entry:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if not verify_password(payload.current_password, auth_entry.password_hash):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")

    auth_entry.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Mot de passe mis à jour"}

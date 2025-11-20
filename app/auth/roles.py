from fastapi import Depends, HTTPException

from app.dependencies.auth import get_current_user
from app.models.users import Users


async def require_admin_or_creator(
    tontine_creator_id: str,
    current_user: Users = Depends(get_current_user)
):
    # Admin passe toujours
    if current_user.role == "admin":
        return current_user

    # Sinon, seulement le créateur de la tontine
    if str(current_user.user_id) != str(tontine_creator_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    return current_user

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.logger import get_logger
from app.models.users import Users
from app.schemas.users import UserTokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
logger = get_logger("auth")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Users:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str | None = payload.get("sub")

        if not user_id:
            logger.warning("❌ Token invalide : champ 'sub' manquant")
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as e:
        logger.error(f"❌ Erreur JWT : {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    # 🔹 Sélection plus légère, sans charger toute la table
    stmt = select(
        Users.user_id,
        Users.email,
        Users.full_name,
        Users.role,
        Users.status
        
    ).where(Users.user_id == user_id)


    result = await db.execute(stmt)
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    #if  row["suspended"] or row["closed"] :
     #   raise HTTPException(status_code=403, detail="User inactive")

    logger.info(f"✅ Authentifié : {row['email']} ({row['role']})")

    # Optionnel : reconstruire un objet Users léger
    user = Users(
        user_id=row["user_id"],
        email=row["email"],
        full_name=row["full_name"],
        role=row["role"],
        status=row["status"],
    )

    return user


# Explicit alias for lightweight auth usage (JWT + minimal DB fields).
get_current_user_light = get_current_user

# 🧩 Version 1 — légère (JWT uniquement)
async def get_current_user_token(token: str = Depends(oauth2_scheme)) -> UserTokenData:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return UserTokenData(user_id=user_id, email=email)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# 🧩 Version 2 — ORM complète (ancien comportement)
async def get_current_user_db(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token invalide")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token expiré ou invalide")

    query = select(Users).where(Users.user_id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    return user

async def get_current_agent(current_user: Users = Depends(get_current_user_db)) -> Users:
    if current_user.role not in ("agent", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux agents"
        )
    return current_user


async def get_current_admin(current_user: Users = Depends(get_current_user_db)) -> Users:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="⛔ Accès réservé aux admin"
        )
    return current_user

# app/auth/dependencies.py
from fastapi import Depends, HTTPException, WebSocket
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.users import Users
from fastapi import Request

async def get_current_user_ws(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
    except JWTError:
        await websocket.close(code=4002)
        return

    user = await db.get(Users, user_id)
    if not user:
        await websocket.close(code=4003)
        return

    return user

# Optional auth helper for reset-password fallback
async def get_optional_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Users | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None

    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    return user



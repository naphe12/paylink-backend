import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.users import Users

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "secret-paylink-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24h
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hachage et vérif mot de passe
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# JWT
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "token_type": "bearer"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


from fastapi import HTTPException, status


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
        ) from e
# ============================================================
# 🔵 RÉCUPÉRATION UTILISATEUR COURANT
# ============================================================
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Users:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

    user_id = payload["sub"]
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    return user

async def get_current_agent(current_user: Users = Depends(get_current_user)) -> Users:
    if current_user.role != "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="⛔ Accès réservé aux agents"
        )
    return current_user

# app/core/security.py
from jose import jwt
from app.core.config import settings

def decode_jwt(token: str):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


from fastapi import Depends, HTTPException, status
from app.models.users import Users
from app.dependencies.auth import get_current_user  # ton auth actuel


def admin_required(current_user: Users = Depends(get_current_user)):
    if current_user.role not in ("admin", "agent"):  # tu peux réduire à "admin"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'administration"
        )
    return current_user

async def agent_required(user: Users = Depends(get_current_user)):
    if str(user.role) not in {"agent","admin"}:
        raise HTTPException(403, "Agent requis")

# Variante WS si tu passes ?token=...
#async def admin_required_ws(websocket: WebSocket, token: str = Query(...)):
    # decode token -> user -> check role (à implémenter selon ton JWT)




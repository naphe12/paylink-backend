from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.logger import get_logger
from app.models.users import Users
from app.schemas.users import UserTokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
logger = get_logger("auth")


def _extract_bearer(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    parts = raw_value.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def _resolve_token(token: str | None, request: Request) -> str:
    resolved = token
    if not resolved:
        resolved = _extract_bearer(request.headers.get("Authorization"))
    if not resolved:
        resolved = request.headers.get("X-Access-Token")
    if resolved and resolved.lower().startswith("bearer "):
        resolved = resolved.split(" ", 1)[1].strip()
    if not resolved:
        resolved = request.cookies.get("access_token") or request.cookies.get("token")
    if not resolved:
        logger.warning(
            f"Auth token missing on {request.url.path} "
            f"(auth={bool(request.headers.get('Authorization'))}, "
            f"x_access={bool(request.headers.get('X-Access-Token'))}, "
            f"cookie_access={bool(request.cookies.get('access_token'))}, "
            f"cookie_token={bool(request.cookies.get('token'))})"
        )
        raise HTTPException(status_code=401, detail="Not authenticated")
    return resolved


def _decode_token(token: str, request: Request) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        logger.warning(f"Invalid/expired token on {request.url.path}: {exc}")
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Users:
    token = _resolve_token(token, request)
    payload = _decode_token(token, request)
    user_id: str | None = payload.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    stmt = select(
        Users.user_id,
        Users.email,
        Users.full_name,
        Users.role,
        Users.status,
    ).where(Users.user_id == user_id)

    result = await db.execute(stmt)
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return Users(
        user_id=row["user_id"],
        email=row["email"],
        full_name=row["full_name"],
        role=row["role"],
        status=row["status"],
    )


get_current_user_light = get_current_user


async def get_current_user_token(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> UserTokenData:
    token = _resolve_token(token, request)
    payload = _decode_token(token, request)

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    return UserTokenData(user_id=user_id, email=email)


async def get_current_user_db(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Users:
    token = _resolve_token(token, request)
    payload = _decode_token(token, request)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    query = select(Users).where(Users.user_id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouve")
    return user


async def get_current_agent(current_user: Users = Depends(get_current_user_db)) -> Users:
    if current_user.role not in ("agent", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux agents",
        )
    return current_user


async def get_current_admin(current_user: Users = Depends(get_current_user_db)) -> Users:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux admin",
        )
    return current_user


async def get_current_user_ws(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
    except JWTError:
        await websocket.close(code=4002)
        return None

    user = await db.get(Users, user_id)
    if not user:
        await websocket.close(code=4003)
        return None
    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Users | None:
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

    return await db.scalar(select(Users).where(Users.user_id == user_id))

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.users import Users


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cookie_secure() -> bool:
    return bool(settings.AUTH_COOKIE_SECURE or settings.APP_ENV == "prod")


def _cookie_domain() -> str | None:
    raw = str(settings.AUTH_COOKIE_DOMAIN or "").strip()
    return raw or None


def _cookie_samesite() -> str:
    value = str(settings.AUTH_COOKIE_SAMESITE or "lax").strip().lower()
    return value if value in {"lax", "strict", "none"} else "lax"


def _refresh_cookie_kwargs() -> dict:
    kwargs = {
        "httponly": True,
        "secure": _cookie_secure(),
        "samesite": _cookie_samesite(),
        "path": settings.AUTH_REFRESH_COOKIE_PATH,
    }
    domain = _cookie_domain()
    if domain:
        kwargs["domain"] = domain
    return kwargs


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=_cookie_domain(),
    )


def get_csrf_header_value(request: Request) -> str:
    header_name = str(settings.AUTH_CSRF_HEADER_NAME or "X-CSRF-Token")
    csrf_value = request.headers.get(header_name)
    if not csrf_value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing")
    return csrf_value


def get_request_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


def get_request_user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:500] if value else None


async def ensure_auth_refresh_schema(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.auth_refresh_tokens (
              id bigserial PRIMARY KEY,
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              token_hash text NOT NULL UNIQUE,
              csrf_token text NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              expires_at timestamptz NOT NULL,
              last_used_at timestamptz NULL,
              revoked_at timestamptz NULL,
              replaced_by_token_hash text NULL,
              user_agent text NULL,
              ip_address text NULL
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_user_id
            ON paylink.auth_refresh_tokens (user_id)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_expires_at
            ON paylink.auth_refresh_tokens (expires_at)
            """
        )
    )


async def issue_refresh_session(
    db: AsyncSession,
    response: Response,
    user: Users,
    request: Request,
) -> str:
    refresh_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(24)
    token_hash = _hash_token(refresh_token)
    refresh_days = settings.refresh_token_expire_days_for_role(getattr(user, "role", None))
    expires_at = _utcnow() + timedelta(days=refresh_days)

    await db.execute(
        text(
            """
            INSERT INTO paylink.auth_refresh_tokens
            (user_id, token_hash, csrf_token, expires_at, user_agent, ip_address)
            VALUES (:user_id, :token_hash, :csrf_token, :expires_at, :user_agent, :ip_address)
            """
        ),
        {
            "user_id": str(user.user_id),
            "token_hash": token_hash,
            "csrf_token": csrf_token,
            "expires_at": expires_at,
            "user_agent": get_request_user_agent(request),
            "ip_address": get_request_ip(request),
        },
    )

    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=int(timedelta(days=refresh_days).total_seconds()),
        **_refresh_cookie_kwargs(),
    )
    return csrf_token


async def rotate_refresh_session(
    db: AsyncSession,
    request: Request,
    response: Response,
) -> dict:
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    token_hash = _hash_token(refresh_token)
    row = (
        await db.execute(
            text(
                """
                SELECT id, user_id, csrf_token, expires_at, revoked_at
                FROM paylink.auth_refresh_tokens
                WHERE token_hash = :token_hash
                """
            ),
            {"token_hash": token_hash},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if row["revoked_at"] is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    if row["expires_at"] <= _utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    csrf_value = get_csrf_header_value(request)
    if csrf_value != row["csrf_token"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    user = await db.get(Users, row["user_id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    new_refresh_token = secrets.token_urlsafe(48)
    new_csrf_token = secrets.token_urlsafe(24)
    new_token_hash = _hash_token(new_refresh_token)
    refresh_days = settings.refresh_token_expire_days_for_role(getattr(user, "role", None))
    expires_at = _utcnow() + timedelta(days=refresh_days)

    await db.execute(
        text(
            """
            UPDATE paylink.auth_refresh_tokens
            SET revoked_at = now(),
                last_used_at = now(),
                replaced_by_token_hash = :replaced_by_token_hash
            WHERE id = :id
            """
        ),
        {
            "id": row["id"],
            "replaced_by_token_hash": new_token_hash,
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO paylink.auth_refresh_tokens
            (user_id, token_hash, csrf_token, expires_at, user_agent, ip_address)
            VALUES (:user_id, :token_hash, :csrf_token, :expires_at, :user_agent, :ip_address)
            """
        ),
        {
            "user_id": str(user.user_id),
            "token_hash": new_token_hash,
            "csrf_token": new_csrf_token,
            "expires_at": expires_at,
            "user_agent": get_request_user_agent(request),
            "ip_address": get_request_ip(request),
        },
    )

    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=new_refresh_token,
        max_age=int(timedelta(days=refresh_days).total_seconds()),
        **_refresh_cookie_kwargs(),
    )
    return {"user": user, "csrf_token": new_csrf_token}


async def revoke_refresh_session(
    db: AsyncSession,
    request: Request,
    response: Response,
    require_csrf: bool = True,
) -> None:
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if not refresh_token:
        clear_refresh_cookie(response)
        return

    token_hash = _hash_token(refresh_token)
    row = (
        await db.execute(
            text(
                """
                SELECT id, csrf_token, revoked_at
                FROM paylink.auth_refresh_tokens
                WHERE token_hash = :token_hash
                """
            ),
            {"token_hash": token_hash},
        )
    ).mappings().first()

    if row and row["revoked_at"] is None:
        if require_csrf:
            csrf_value = get_csrf_header_value(request)
            if csrf_value != row["csrf_token"]:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
        await db.execute(
            text(
                """
                UPDATE paylink.auth_refresh_tokens
                SET revoked_at = now(), last_used_at = now()
                WHERE id = :id
                """
            ),
            {"id": row["id"]},
        )

    clear_refresh_cookie(response)

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies.auth import get_current_admin
from app.core.database import get_db
from app.models.users import Users
from app.security.redis_client import get_redis
from app.services.auth_sessions import get_request_ip, get_request_user_agent
from app.services.audit_service import audit_log


_LOCAL_STEP_UP_TOKENS: dict[str, dict] = {}
_STEP_UP_ENFORCEMENT_ENABLED = False


def _is_production_env() -> bool:
    return str(getattr(settings, "APP_ENV", "") or "").strip().lower() in {"prod", "production"}


def is_admin_step_up_header_fallback_enabled() -> bool:
    if _is_production_env():
        return False
    return bool(getattr(settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_step_up_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _step_up_store_key(jti: str) -> str:
    return f"admin_step_up:{jti}"


def _get_step_up_target_context(request: Request) -> tuple[str | None, str | None]:
    path_params = getattr(request, "path_params", {}) or {}
    if path_params.get("trade_id"):
        return "p2p_trade", str(path_params["trade_id"])
    if path_params.get("order_id"):
        return "escrow_order", str(path_params["order_id"])
    if path_params.get("intent_id"):
        return "payment_intent", str(path_params["intent_id"])
    if path_params.get("payment_id"):
        return "payment", str(path_params["payment_id"])
    return None, None


def _purge_expired_local_step_up_tokens() -> None:
    now = _utcnow()
    expired = [
        key
        for key, item in _LOCAL_STEP_UP_TOKENS.items()
        if datetime.fromisoformat(str(item.get("expires_at"))) <= now
    ]
    for key in expired:
        _LOCAL_STEP_UP_TOKENS.pop(key, None)


def _remember_local_step_up_token(jti: str, record: dict) -> None:
    _purge_expired_local_step_up_tokens()
    _LOCAL_STEP_UP_TOKENS[jti] = record


def _consume_local_step_up_token(jti: str) -> dict | None:
    _purge_expired_local_step_up_tokens()
    return _LOCAL_STEP_UP_TOKENS.pop(jti, None)


async def _persist_step_up_token(jti: str, record: dict) -> None:
    redis = get_redis()
    if redis is None:
        return
    ttl_seconds = max(
        int((datetime.fromisoformat(str(record["expires_at"])) - _utcnow()).total_seconds()),
        1,
    )
    await redis.set(_step_up_store_key(jti), json.dumps(record), ex=ttl_seconds)


async def _consume_persisted_step_up_token(jti: str) -> dict | None:
    redis = get_redis()
    if redis is None:
        return None
    key = _step_up_store_key(jti)
    raw = None
    getdel = getattr(redis, "getdel", None)
    if callable(getdel):
        raw = await getdel(key)
    else:
        raw = await redis.get(key)
        if raw is not None:
            await redis.delete(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def _audit_admin_step_up(
    db: AsyncSession | object | None,
    *,
    request: Request,
    current_admin: Users,
    action: str,
    outcome: str,
    code: str,
    method: str | None,
    status_code: int,
) -> None:
    if db is None or not hasattr(db, "execute"):
        return
    target_type, target_id = _get_step_up_target_context(request)
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    try:
        await audit_log(
            db,
            actor_user_id=str(getattr(current_admin, "user_id", "") or "") or None,
            actor_role=str(getattr(current_admin, "role", "") or "") or None,
            action="ADMIN_STEP_UP_CHECK",
            entity_type=target_type or "ADMIN_STEP_UP",
            entity_id=target_id,
            before_state=None,
            after_state={
                "requested_action": action,
                "outcome": outcome,
                "code": code,
                "method": method,
                "status_code": status_code,
                "request_id": request_id,
                "target_type": target_type,
                "target_id": target_id,
            },
            ip=get_request_ip(request),
            user_agent=get_request_user_agent(request),
        )
    except Exception:
        return


def create_admin_step_up_token(*, user: Users, action: str | None = None) -> str:
    expires_delta = timedelta(minutes=max(int(settings.ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES or 5), 1))
    expires_at = _utcnow() + expires_delta
    jti = secrets.token_urlsafe(18)
    payload = {
        "sub": str(user.user_id),
        "role": str(getattr(user, "role", "") or ""),
        "action": "admin_step_up",
        "step_up_action": str(action or "*"),
        "jti": jti,
        "iat": int(_utcnow().timestamp()),
    }
    payload["exp"] = expires_at
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    _remember_local_step_up_token(
        jti,
        {
            "token_hash": _hash_step_up_token(token),
            "user_id": str(user.user_id),
            "step_up_action": str(action or "*"),
            "expires_at": expires_at.isoformat(),
        },
    )
    return token


async def register_admin_step_up_token(*, token: str, user: Users, action: str | None = None) -> None:
    try:
        payload = jwt.get_unverified_claims(token)
    except JWTError:
        return
    jti = str(payload.get("jti") or "").strip()
    if not jti:
        return
    expires_at = payload.get("exp")
    if isinstance(expires_at, (int, float)):
        expires_value = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    else:
        expires_value = datetime.fromisoformat(str(expires_at))
        if expires_value.tzinfo is None:
            expires_value = expires_value.replace(tzinfo=timezone.utc)
    await _persist_step_up_token(
        jti,
        {
            "token_hash": _hash_step_up_token(token),
            "user_id": str(getattr(user, "user_id", "") or ""),
            "step_up_action": str(action or "*"),
            "expires_at": expires_value.isoformat(),
        },
    )


def _read_bearer_access_token(request: Request) -> str | None:
    raw = str(request.headers.get("authorization") or "").strip()
    if not raw.lower().startswith("bearer "):
        return None
    token = raw[7:].strip()
    return token or None


async def bind_admin_step_up_token_to_request(*, token: str, request: Request) -> None:
    access_token = _read_bearer_access_token(request)
    if not access_token:
        return
    try:
        payload = jwt.get_unverified_claims(token)
    except JWTError:
        return
    jti = str(payload.get("jti") or "").strip()
    if not jti:
        return
    record = _LOCAL_STEP_UP_TOKENS.get(jti)
    if record is None:
        return
    record["access_token_hash"] = _hash_step_up_token(access_token)
    _remember_local_step_up_token(jti, record)
    await _persist_step_up_token(jti, record)


def _read_header(request: Request, header_name: str) -> str | None:
    return request.headers.get(header_name)


async def _validate_step_up_token(token: str, *, request: Request, current_admin: Users, action: str) -> None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_admin_step_up_token",
                "message": "Jeton de confirmation admin invalide ou expire.",
                "action": action,
            },
        ) from exc

    if str(payload.get("action") or "") != "admin_step_up":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_admin_step_up_token",
                "message": "Jeton de confirmation admin invalide.",
                "action": action,
            },
        )

    token_jti = str(payload.get("jti") or "").strip()
    if not token_jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_admin_step_up_token",
                "message": "Jeton de confirmation admin invalide.",
                "action": action,
            },
        )

    if str(payload.get("sub") or "") != str(getattr(current_admin, "user_id", "") or ""):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_step_up_user_mismatch",
                "message": "Le jeton de confirmation admin ne correspond pas a cet utilisateur.",
                "action": action,
            },
        )

    token_action = str(payload.get("step_up_action") or "*").strip() or "*"
    if token_action not in {"*", action}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_step_up_action_mismatch",
                "message": "Le jeton de confirmation admin n'est pas valable pour cette action.",
                "action": action,
            },
        )

    record = await _consume_persisted_step_up_token(token_jti)
    if record is None:
        record = _consume_local_step_up_token(token_jti)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "admin_step_up_token_reused",
                "message": "Le jeton de confirmation admin a deja ete utilise ou n'est plus disponible.",
                "action": action,
            },
        )

    if str(record.get("user_id") or "") != str(getattr(current_admin, "user_id", "") or ""):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_step_up_user_mismatch",
                "message": "Le jeton de confirmation admin ne correspond pas a cet utilisateur.",
                "action": action,
            },
        )

    stored_action = str(record.get("step_up_action") or "*").strip() or "*"
    if stored_action not in {"*", action}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_step_up_action_mismatch",
                "message": "Le jeton de confirmation admin n'est pas valable pour cette action.",
                "action": action,
            },
        )

    if str(record.get("token_hash") or "") != _hash_step_up_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_admin_step_up_token",
                "message": "Jeton de confirmation admin invalide.",
                "action": action,
            },
        )

    expected_access_token_hash = str(record.get("access_token_hash") or "").strip()
    if expected_access_token_hash:
        current_access_token = _read_bearer_access_token(request)
        if not current_access_token or _hash_step_up_token(current_access_token) != expected_access_token_hash:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "admin_step_up_session_mismatch",
                    "message": "Le jeton de confirmation admin n'est valable que pour la session qui l'a emis.",
                    "action": action,
                },
            )


def require_admin_step_up(action: str):
    async def _dependency(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_admin: Users = Depends(get_current_admin),
    ) -> Users:
        if not _STEP_UP_ENFORCEMENT_ENABLED:
            # Step-up protection globally disabled by product decision.
            # Keep dependency signature unchanged to avoid touching all routers.
            return current_admin

        token_header_name = str(settings.ADMIN_STEP_UP_TOKEN_HEADER_NAME or "X-Admin-Step-Up-Token").strip()
        step_up_token = _read_header(request, token_header_name)
        if step_up_token:
            try:
                await _validate_step_up_token(step_up_token, request=request, current_admin=current_admin, action=action)
            except HTTPException as exc:
                await _audit_admin_step_up(
                    db,
                    request=request,
                    current_admin=current_admin,
                    action=action,
                    outcome="denied",
                    code=str(getattr(exc, "detail", {}).get("code") or "admin_step_up_denied"),
                    method="token",
                    status_code=int(getattr(exc, "status_code", status.HTTP_401_UNAUTHORIZED)),
                )
                if hasattr(db, "commit"):
                    await db.commit()
                raise
            await _audit_admin_step_up(
                db,
                request=request,
                current_admin=current_admin,
                action=action,
                outcome="verified",
                code="admin_step_up_verified",
                method="token",
                status_code=status.HTTP_200_OK,
            )
            if hasattr(db, "commit"):
                await db.commit()
            request.state.admin_step_up_verified = True
            request.state.admin_step_up_action = action
            request.state.admin_step_up_user_id = str(getattr(current_admin, "user_id", "") or "")
            request.state.admin_step_up_method = "token"
            return current_admin

        if not is_admin_step_up_header_fallback_enabled():
            await _audit_admin_step_up(
                db,
                request=request,
                current_admin=current_admin,
                action=action,
                outcome="required",
                code="admin_step_up_required",
                method=None,
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            )
            if hasattr(db, "commit"):
                await db.commit()
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "code": "admin_step_up_required",
                    "message": "Jeton de confirmation admin requis pour cette action.",
                    "action": action,
                    "token_header_name": token_header_name,
                    "header_fallback_enabled": False,
                },
            )

        confirm_header_name = str(settings.ADMIN_STEP_UP_HEADER_NAME or "X-Admin-Confirm").strip()
        expected_value = str(settings.ADMIN_STEP_UP_EXPECTED_VALUE or "confirm").strip()
        actual_value = str(_read_header(request, confirm_header_name) or "").strip()
        if actual_value.lower() != expected_value.lower():
            await _audit_admin_step_up(
                db,
                request=request,
                current_admin=current_admin,
                action=action,
                outcome="required",
                code="admin_step_up_required",
                method="header",
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            )
            if hasattr(db, "commit"):
                await db.commit()
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "code": "admin_step_up_required",
                    "message": "Confirmation admin supplementaire requise pour cette action.",
                    "action": action,
                    "header_name": confirm_header_name,
                    "token_header_name": token_header_name,
                    "header_fallback_enabled": True,
                },
            )

        await _audit_admin_step_up(
            db,
            request=request,
            current_admin=current_admin,
            action=action,
            outcome="verified",
            code="admin_step_up_verified",
            method="header",
            status_code=status.HTTP_200_OK,
        )
        if hasattr(db, "commit"):
            await db.commit()
        request.state.admin_step_up_verified = True
        request.state.admin_step_up_action = action
        request.state.admin_step_up_user_id = str(getattr(current_admin, "user_id", "") or "")
        request.state.admin_step_up_method = "header"
        return current_admin

    return _dependency


def get_admin_step_up_method(request: Request) -> str | None:
    return getattr(getattr(request, "state", None), "admin_step_up_method", None)

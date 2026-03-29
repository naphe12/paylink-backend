from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from app.config import settings
from app.dependencies.auth import get_current_admin
from app.models.users import Users


def create_admin_step_up_token(*, user: Users, action: str | None = None) -> str:
    expires_delta = timedelta(minutes=max(int(settings.ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES or 5), 1))
    payload = {
        "sub": str(user.user_id),
        "role": str(getattr(user, "role", "") or ""),
        "action": "admin_step_up",
        "step_up_action": str(action or "*"),
    }
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _read_header(request: Request, header_name: str) -> str | None:
    return request.headers.get(header_name)


def _validate_step_up_token(token: str, *, current_admin: Users, action: str) -> None:
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


def require_admin_step_up(action: str):
    async def _dependency(
        request: Request,
        current_admin: Users = Depends(get_current_admin),
    ) -> Users:
        if not settings.ADMIN_STEP_UP_ENABLED:
            return current_admin

        token_header_name = str(settings.ADMIN_STEP_UP_TOKEN_HEADER_NAME or "X-Admin-Step-Up-Token").strip()
        step_up_token = _read_header(request, token_header_name)
        if step_up_token:
            _validate_step_up_token(step_up_token, current_admin=current_admin, action=action)
            request.state.admin_step_up_verified = True
            request.state.admin_step_up_action = action
            request.state.admin_step_up_user_id = str(getattr(current_admin, "user_id", "") or "")
            request.state.admin_step_up_method = "token"
            return current_admin

        if not bool(getattr(settings, "ADMIN_STEP_UP_ALLOW_HEADER_FALLBACK", False)):
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

        request.state.admin_step_up_verified = True
        request.state.admin_step_up_action = action
        request.state.admin_step_up_user_id = str(getattr(current_admin, "user_id", "") or "")
        request.state.admin_step_up_method = "header"
        return current_admin

    return _dependency


def get_admin_step_up_method(request: Request) -> str | None:
    return getattr(getattr(request, "state", None), "admin_step_up_method", None)

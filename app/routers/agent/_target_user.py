import re
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import Users


_TARGET_TOKEN_RE = re.compile(
    r"(?i)(?P<prefix>\b(?:user|client|email|phone|paytag)\s*:\s*)(?P<value>[^\s,;]+)"
)


@dataclass(slots=True)
class ResolvedTargetUser:
    user_id: UUID | None
    message: str


def _is_admin(current_user) -> bool:
    return str(getattr(current_user, "role", "") or "").lower() == "admin"


def _cleanup_message(message: str, match: re.Match[str] | None) -> str:
    if match is None:
        return message
    cleaned = f"{message[:match.start()]} {message[match.end():]}".strip()
    return re.sub(r"\s+", " ", cleaned)


def _extract_target_token(message: str) -> tuple[str, str, str]:
    match = _TARGET_TOKEN_RE.search(message or "")
    if match is None:
        return "", "", message
    prefix = str(match.group("prefix") or "").split(":", 1)[0].strip().lower()
    value = str(match.group("value") or "").strip()
    return prefix, value, _cleanup_message(message, match)


async def _resolve_identifier(db: AsyncSession, identifier: str) -> UUID | None:
    compact = re.sub(r"\s+", "", identifier or "").strip()
    if not compact:
        return None

    try:
        return UUID(compact)
    except ValueError:
        pass

    lowered = compact.lower()
    phone_candidates = [compact]
    if compact.isdigit():
        phone_candidates.append(f"+{compact}")

    stmt = select(Users.user_id).where(
        or_(
            func.lower(Users.email) == lowered,
            func.lower(Users.paytag) == lowered,
            Users.phone_e164.in_(phone_candidates),
        )
    )
    return await db.scalar(stmt)


async def _resolve_prompt_target_user_id(
    db: AsyncSession,
    token_type: str,
    token_value: str,
) -> UUID | None:
    token_type = (token_type or "").lower()
    token_value = str(token_value or "").strip()
    if not token_type or not token_value:
        return None

    if token_type in {"user", "client"}:
        return await _resolve_identifier(db, token_value)

    if token_type == "email":
        return await db.scalar(
            select(Users.user_id).where(func.lower(Users.email) == token_value.lower())
        )

    if token_type == "paytag":
        return await db.scalar(
            select(Users.user_id).where(func.lower(Users.paytag) == token_value.lower())
        )

    if token_type == "phone":
        compact = re.sub(r"\s+", "", token_value)
        phone_candidates = [compact]
        if compact.isdigit():
            phone_candidates.append(f"+{compact}")
        return await db.scalar(
            select(Users.user_id).where(Users.phone_e164.in_(phone_candidates))
        )

    return None


async def resolve_target_user_context(
    db: AsyncSession,
    current_user,
    target_user_id: UUID | None = None,
    message: str = "",
) -> ResolvedTargetUser:
    if not _is_admin(current_user):
        return ResolvedTargetUser(
            user_id=getattr(current_user, "user_id", None),
            message=message,
        )

    token_type, token_value, cleaned_message = _extract_target_token(message)
    if target_user_id:
        return ResolvedTargetUser(user_id=target_user_id, message=cleaned_message)

    if token_type:
        resolved_user_id = await _resolve_prompt_target_user_id(db, token_type, token_value)
        if resolved_user_id is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Utilisateur cible introuvable dans le prompt. "
                    "Utilisez user:, client:, email:, phone: ou paytag: avec une valeur exacte."
                ),
            )
        return ResolvedTargetUser(user_id=resolved_user_id, message=cleaned_message)

    return ResolvedTargetUser(
        user_id=getattr(current_user, "user_id", None),
        message=message,
    )


def resolve_target_user_id(current_user, target_user_id: UUID | None = None):
    if _is_admin(current_user) and target_user_id:
        return target_user_id
    return getattr(current_user, "user_id", None)

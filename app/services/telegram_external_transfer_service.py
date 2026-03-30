from __future__ import annotations

import inspect
import logging
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from jose import JWTError, jwt
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_chat.schemas import AgentChatDraft
from app.agent_chat.service import process_chat_message
from app.agent_chat.utils import apply_selected_beneficiary
from app.config import settings
from app.core.security import create_access_token
from app.models.external_beneficiaries import ExternalBeneficiaries
from app.models.external_transfers import ExternalTransfers
from app.models.users import Users
from app.routers.wallet.transfer import _external_transfer_core
from app.schemas.external_transfers import ExternalTransferCreate, ExternalTransferRead
from app.services.telegram import send_message as send_telegram_message


LINK_TOKEN_ACTION = "telegram_external_transfer_link"
logger = logging.getLogger(__name__)


def _normalize_beneficiary_account(value: str | None) -> str:
    return str(value or "").strip().lower()


async def ensure_telegram_external_transfer_schema(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.telegram_chat_links (
              chat_id text PRIMARY KEY,
              user_id uuid NOT NULL UNIQUE REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              linked_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.telegram_chat_states (
              chat_id text PRIMARY KEY,
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              draft jsonb NULL,
              raw_message text NULL,
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.commit()


def build_telegram_link_token(*, user_id: str) -> dict[str, str]:
    token = create_access_token(
        data={"sub": str(user_id), "action": LINK_TOKEN_ACTION},
        expires_delta=timedelta(hours=12),
    )
    bot_username = str(getattr(settings, "TELEGRAM_BOT_USERNAME", "") or "").strip().lstrip("@")
    return {
        "token": token,
        "command": f"/link {token}",
        "bot_username": bot_username or "",
        "bot_url": f"https://t.me/{bot_username}" if bot_username else "",
    }


def _decode_link_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Jeton Telegram invalide ou expire.") from exc
    if payload.get("action") != LINK_TOKEN_ACTION or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Jeton Telegram invalide.")
    return str(payload["sub"])


async def link_chat_to_user(
    db: AsyncSession,
    *,
    chat_id: str,
    token: str,
) -> Users:
    user_id = _decode_link_token(token)
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    await db.execute(
        text(
            """
            INSERT INTO paylink.telegram_chat_links (chat_id, user_id, linked_at, updated_at)
            VALUES (:chat_id, CAST(:user_id AS uuid), now(), now())
            ON CONFLICT (chat_id)
            DO UPDATE SET user_id = EXCLUDED.user_id, updated_at = now()
            """
        ),
        {"chat_id": str(chat_id).strip(), "user_id": user_id},
    )
    await db.execute(
        text(
            """
            DELETE FROM paylink.telegram_chat_states
            WHERE chat_id = :chat_id
            """
        ),
        {"chat_id": str(chat_id).strip()},
    )
    await db.commit()
    return user


async def get_linked_user(db: AsyncSession, *, chat_id: str) -> Users | None:
    row = (
        await db.execute(
            text(
                """
                SELECT user_id
                FROM paylink.telegram_chat_links
                WHERE chat_id = :chat_id
                LIMIT 1
                """
            ),
            {"chat_id": str(chat_id).strip()},
        )
    ).mappings().first()
    if not row:
        return None
    return await db.scalar(select(Users).where(Users.user_id == row["user_id"]))


async def store_chat_state(
    db: AsyncSession,
    *,
    chat_id: str,
    user_id: str,
    draft: AgentChatDraft | None,
    raw_message: str | None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO paylink.telegram_chat_states (chat_id, user_id, draft, raw_message, updated_at)
            VALUES (:chat_id, CAST(:user_id AS uuid), CAST(:draft AS jsonb), :raw_message, now())
            ON CONFLICT (chat_id)
            DO UPDATE SET
              user_id = EXCLUDED.user_id,
              draft = EXCLUDED.draft,
              raw_message = EXCLUDED.raw_message,
              updated_at = now()
            """
        ),
        {
            "chat_id": str(chat_id).strip(),
            "user_id": str(user_id),
            "draft": draft.model_dump_json() if draft is not None else None,
            "raw_message": str(raw_message or "").strip() or None,
        },
    )
    await db.commit()


async def load_chat_state(db: AsyncSession, *, chat_id: str) -> AgentChatDraft | None:
    row = (
        await db.execute(
            text(
                """
                SELECT draft
                FROM paylink.telegram_chat_states
                WHERE chat_id = :chat_id
                LIMIT 1
                """
            ),
            {"chat_id": str(chat_id).strip()},
        )
    ).mappings().first()
    if not row or not row["draft"]:
        return None
    return AgentChatDraft.model_validate(row["draft"])


async def clear_chat_state(db: AsyncSession, *, chat_id: str) -> None:
    await db.execute(
        text(
            """
            DELETE FROM paylink.telegram_chat_states
            WHERE chat_id = :chat_id
            """
        ),
        {"chat_id": str(chat_id).strip()},
    )
    await db.commit()


async def _save_beneficiary_from_chat(
    db: AsyncSession,
    *,
    current_user: Users,
    draft: AgentChatDraft,
) -> dict[str, Any]:
    existing = await db.scalar(
        select(ExternalBeneficiaries).where(
            ExternalBeneficiaries.user_id == current_user.user_id,
            ExternalBeneficiaries.partner_name == str(draft.partner_name or ""),
            ExternalBeneficiaries.recipient_phone == str(draft.recipient_phone or ""),
            func.coalesce(func.lower(ExternalBeneficiaries.recipient_email), "") == _normalize_beneficiary_account(draft.account_ref),
        )
    )
    if existing is None:
        existing = ExternalBeneficiaries(
            user_id=current_user.user_id,
            recipient_name=str(draft.recipient or ""),
            recipient_phone=str(draft.recipient_phone or ""),
            recipient_email=_normalize_beneficiary_account(draft.account_ref) or None,
            partner_name=str(draft.partner_name or ""),
            country_destination=str(draft.country_destination or ""),
            is_active=True,
        )
        db.add(existing)
        message_out = f"Beneficiaire {existing.recipient_name} enregistre avec succes."
    else:
        existing.recipient_name = str(draft.recipient or existing.recipient_name)
        existing.recipient_email = _normalize_beneficiary_account(draft.account_ref) or existing.recipient_email
        existing.country_destination = str(draft.country_destination or existing.country_destination)
        existing.is_active = True
        message_out = f"Beneficiaire {existing.recipient_name} mis a jour avec succes."
    await db.commit()
    return {
        "message": message_out,
        "beneficiary": {
            "recipient_name": existing.recipient_name,
            "recipient_phone": existing.recipient_phone,
            "account_ref": existing.recipient_email,
            "partner_name": existing.partner_name,
            "country_destination": existing.country_destination,
        },
    }


async def _run_background_tasks(background_tasks: BackgroundTasks) -> None:
    for task in getattr(background_tasks, "tasks", []):
        result = task.func(*task.args, **task.kwargs)
        if inspect.isawaitable(result):
            await result


async def confirm_external_transfer_from_chat(
    db: AsyncSession,
    *,
    chat_id: str,
    current_user: Users,
) -> dict[str, Any]:
    draft = await load_chat_state(db, chat_id=chat_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Aucun brouillon en attente pour ce chat.")

    missing_fields: list[str] = []
    if not draft.partner_name:
        missing_fields.append("partner_name")
    if not draft.country_destination:
        missing_fields.append("country_destination")
    if not draft.recipient_phone:
        missing_fields.append("recipient_phone")
    if not draft.amount:
        missing_fields.append("amount")
    if not draft.recipient:
        missing_fields.append("recipient")
    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Brouillon incomplet: {', '.join(missing_fields)}",
        )

    background_tasks = BackgroundTasks()
    transfer = await _external_transfer_core(
        data=ExternalTransferCreate(
            partner_name=draft.partner_name,
            country_destination=draft.country_destination,
            recipient_name=draft.recipient,
            recipient_phone=draft.recipient_phone,
            amount=draft.amount,
        ),
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
        override_context={
            "source": "telegram_external_transfer",
            "origin_chat_id": str(chat_id).strip(),
        },
    )
    await _run_background_tasks(background_tasks)

    transfer_id = getattr(transfer, "transfer_id", None)
    if transfer_id is None and isinstance(transfer, dict):
        transfer_id = transfer.get("transfer_id")
    if transfer_id:
        transfer_row = await db.scalar(
            select(ExternalTransfers).where(ExternalTransfers.transfer_id == transfer_id)
        )
        if transfer_row:
            metadata = dict(getattr(transfer_row, "metadata_", {}) or {})
            metadata["chat_memory"] = {
                "source": "telegram_external_transfer",
                "raw_message": str(draft.raw_message or "").strip(),
                "recipient_input": str(draft.recipient or "").strip(),
                "recipient_name": str(transfer_row.recipient_name or draft.recipient or "").strip(),
                "recipient_phone": str(transfer_row.recipient_phone or draft.recipient_phone or "").strip(),
                "partner_name": str(transfer_row.partner_name or draft.partner_name or "").strip(),
                "country_destination": str(
                    transfer_row.country_destination or draft.country_destination or ""
                ).strip(),
            }
            transfer_row.metadata_ = metadata
            await db.commit()

    await clear_chat_state(db, chat_id=chat_id)
    transfer_payload = (
        ExternalTransferRead.model_validate(transfer).model_dump(mode="json")
        if not isinstance(transfer, dict)
        else transfer
    )
    return transfer_payload


async def confirm_chat_action(
    db: AsyncSession,
    *,
    chat_id: str,
    current_user: Users,
) -> dict[str, Any]:
    draft = await load_chat_state(db, chat_id=chat_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Aucun brouillon en attente pour ce chat.")

    draft = apply_selected_beneficiary(draft)
    if draft.intent == "beneficiary_add":
        missing_fields: list[str] = []
        if not draft.partner_name:
            missing_fields.append("partner_name")
        if not draft.country_destination:
            missing_fields.append("country_destination")
        if not draft.recipient_phone:
            missing_fields.append("recipient_phone")
        if not draft.recipient:
            missing_fields.append("recipient")
        if missing_fields:
            raise HTTPException(status_code=400, detail=f"Brouillon incomplet: {', '.join(missing_fields)}")
        result = await _save_beneficiary_from_chat(db, current_user=current_user, draft=draft)
        await clear_chat_state(db, chat_id=chat_id)
        return {"kind": "beneficiary_add", **result}

    transfer = await confirm_external_transfer_from_chat(
        db,
        chat_id=chat_id,
        current_user=current_user,
    )
    return {"kind": "external_transfer", "transfer": transfer}


def format_chat_response(payload) -> str:
    message = str(getattr(payload, "message", "") or "").strip()
    lines = [message] if message else []
    draft = getattr(payload, "data", None)
    if draft:
        if getattr(draft, "amount", None):
            currency = getattr(draft, "currency", None) or getattr(draft, "wallet_currency", None) or ""
            lines.append(f"Montant: {draft.amount} {currency}".strip())
        if getattr(draft, "recipient", None):
            lines.append(f"Beneficiaire: {draft.recipient}")
        if getattr(draft, "recipient_phone", None):
            lines.append(f"Telephone: {draft.recipient_phone}")
        if getattr(draft, "partner_name", None):
            lines.append(f"Partenaire: {draft.partner_name}")
        if getattr(draft, "country_destination", None):
            lines.append(f"Destination: {draft.country_destination}")
    missing_fields = list(getattr(payload, "missing_fields", []) or [])
    if missing_fields:
        lines.append(f"Champs manquants: {', '.join(missing_fields)}")
    if getattr(payload, "executable", False):
        lines.append("Repondez /confirm pour creer la demande ou /cancel pour annuler.")
    suggestions = list(getattr(payload, "suggestions", []) or [])
    if suggestions:
        lines.append("Suggestions:")
        lines.extend(f"- {item}" for item in suggestions[:3])
    return "\n".join(lines).strip()


async def handle_telegram_external_transfer_message(
    db: AsyncSession,
    *,
    chat_id: str,
    message_text: str,
) -> str:
    text_value = str(message_text or "").strip()
    lowered = text_value.lower()
    if lowered in {"/start", "/help"}:
        return (
            "Assistant transfert externe Paylink.\n"
            "1. Depuis le web, genere un jeton Telegram.\n"
            "2. Envoie ici /link <token>.\n"
            "3. Ecris ensuite ta demande, par ex: envoie 100 EUR a Jean via Lumicash au Burundi au +25761234567\n"
            "4. Reponds /confirm pour creer la demande ou /cancel pour annuler."
        )
    if lowered.startswith("/link "):
        token = text_value.split(" ", 1)[1].strip()
        user = await link_chat_to_user(db, chat_id=chat_id, token=token)
        return (
            f"Compte lie avec succes a {user.full_name or user.email or user.user_id}.\n"
            "Envoyez maintenant votre demande de transfert, puis /confirm pour l'executer."
        )

    current_user = await get_linked_user(db, chat_id=chat_id)
    if not current_user:
        return (
            "Ce chat n'est pas encore lie a un compte Paylink.\n"
            "Depuis l'application web, genere d'abord le jeton Telegram puis envoie /link <token> ici."
        )

    if lowered in {"/cancel", "annuler", "cancel"}:
        await clear_chat_state(db, chat_id=chat_id)
        return "Brouillon annule."

    if lowered in {"/confirm", "confirmer", "confirm"}:
        result = await confirm_chat_action(
            db,
            chat_id=chat_id,
            current_user=current_user,
        )
        if result.get("kind") == "beneficiary_add":
            beneficiary = result.get("beneficiary") or {}
            return (
                f"{result.get('message')}\n"
                f"Beneficiaire: {beneficiary.get('recipient_name')}\n"
                f"Partenaire: {beneficiary.get('partner_name')}\n"
                f"Telephone: {beneficiary.get('recipient_phone')}"
            )
        transfer = result.get("transfer") or {}
        reference = transfer.get("reference_code") or transfer.get("transfer_id")
        status = transfer.get("status") or "pending"
        return f"Demande creee avec succes.\nReference: {reference}\nStatut: {status}"

    normalized_message = text_value
    if lowered.startswith("/transfer "):
        normalized_message = text_value.split(" ", 1)[1].strip()

    current_draft = await load_chat_state(db, chat_id=chat_id)
    if current_draft and current_draft.beneficiary_candidates and lowered.isdigit():
        current_draft.selected_beneficiary_index = int(lowered)
        current_draft = apply_selected_beneficiary(current_draft)
        await store_chat_state(
            db,
            chat_id=chat_id,
            user_id=str(current_user.user_id),
            draft=current_draft,
            raw_message=current_draft.raw_message,
        )
        return (
            f"Beneficiaire {lowered} selectionne.\n"
            f"{format_chat_response(SimpleNamespace(message='Selection prise en compte.', data=current_draft, missing_fields=[], executable=True, suggestions=[]))}"
        )

    payload = await process_chat_message(db, user_id=current_user.user_id, message=normalized_message)
    if getattr(payload, "status", None) in {"CONFIRM", "NEED_INFO"} and getattr(payload, "data", None) is not None:
        await store_chat_state(
            db,
            chat_id=chat_id,
            user_id=str(current_user.user_id),
            draft=getattr(payload, "data", None),
            raw_message=normalized_message,
        )
    else:
        await clear_chat_state(db, chat_id=chat_id)
    return format_chat_response(payload)


async def process_telegram_update(db: AsyncSession, update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "").strip()
    message_text = str(message.get("text") or "").strip()
    if not chat_id or not message_text:
        return {"ok": True, "ignored": True}
    logger.info("Telegram external transfer update chat_id=%s text=%s", chat_id, message_text)
    try:
        reply = await handle_telegram_external_transfer_message(
            db,
            chat_id=chat_id,
            message_text=message_text,
        )
    except HTTPException as exc:
        logger.warning(
            "Telegram external transfer business error chat_id=%s status=%s detail=%s",
            chat_id,
            exc.status_code,
            exc.detail,
        )
        reply = str(exc.detail or "Impossible de traiter cette demande Telegram.")
    except Exception as exc:
        logger.exception(
            "Telegram external transfer unexpected error chat_id=%s text=%s error=%s",
            chat_id,
            message_text,
            exc,
        )
        reply = "Impossible de traiter cette demande Telegram pour le moment."
    await send_telegram_message(int(chat_id), reply)
    return {"ok": True, "chat_id": chat_id}

from fastapi import APIRouter, BackgroundTasks, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_chat.schemas import ChatRequest, ChatResponse, ConfirmChatRequest
from app.agent_chat.service import (
    SUPPORTED_TRANSFER_PARTNERS,
    cancel_chat_request,
    process_chat_message,
)
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.external_transfers import ExternalTransfers
from app.models.users import Users
from app.schemas.external_transfers import ExternalTransferCreate, ExternalTransferRead
from app.routers.wallet.transfer import _external_transfer_core

router = APIRouter(prefix="/agent/chat", tags=["Agent Chat"])


@router.post("", response_model=ChatResponse)
async def chat_agent(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await process_chat_message(db, user_id=current_user.user_id, message=payload.message)


@router.post("/cancel", response_model=ChatResponse)
async def cancel_agent_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_chat_request()


@router.post("/confirm")
async def confirm_agent_chat(
    payload: ConfirmChatRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    draft = payload.draft
    missing_fields = []
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
        return ChatResponse(
            status="NEED_INFO",
            message="Confirmation recue, mais il manque encore des informations pour executer la demande.",
            data=draft,
            missing_fields=missing_fields,
            executable=False,
        )

    if str(draft.partner_name) not in SUPPORTED_TRANSFER_PARTNERS:
        return ChatResponse(
            status="NEED_INFO",
            message=(
                f"Le partenaire {draft.partner_name} n'est pas encore branche au flux automatique. "
                "Utilisez Lumicash, Ecocash ou eNoti pour l'execution directe."
            ),
            data=draft,
            missing_fields=["partner_name"],
            executable=False,
        )

    transfer = await _external_transfer_core(
        data=ExternalTransferCreate(
            partner_name=draft.partner_name,
            country_destination=draft.country_destination,
            recipient_name=draft.recipient,
            recipient_phone=draft.recipient_phone,
            amount=draft.amount,
        ),
        background_tasks=background_tasks,
        idempotency_key=idempotency_key,
        db=db,
        current_user=current_user,
    )

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
                "source": "agent_chat",
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

    transfer_payload = (
        ExternalTransferRead.model_validate(transfer).model_dump(mode="json")
        if not isinstance(transfer, dict)
        else transfer
    )
    return {
        "status": "DONE",
        "message": "Demande creee avec succes.",
        "transfer": transfer_payload,
    }

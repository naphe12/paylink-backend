from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.support_cases import (
    SupportCaseAttachmentCreate,
    SupportCaseCreate,
    SupportCaseDetailRead,
    SupportCaseMessageCreate,
    SupportCaseRead,
    SupportCaseUserStatusUpdate,
)
from app.services.support_case_service import (
    add_support_case_attachment_for_user,
    add_support_case_message_for_user,
    create_support_case,
    get_support_case_detail_for_user,
    list_support_cases_for_user,
    update_support_case_status_for_user,
)

router = APIRouter(prefix="/support/cases", tags=["Support Cases"])


@router.post("", response_model=SupportCaseRead)
async def create_support_case_route(
    payload: SupportCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_support_case(
        db,
        current_user=current_user,
        category=payload.category,
        subject=payload.subject,
        description=payload.description,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )


@router.get("", response_model=list[SupportCaseRead])
async def list_support_cases_route(
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_support_cases_for_user(db, current_user=current_user, status=status)


@router.get("/{case_id}", response_model=SupportCaseDetailRead)
async def get_support_case_detail_route(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_support_case_detail_for_user(db, case_id=case_id, current_user=current_user)


@router.post("/{case_id}/messages", response_model=SupportCaseDetailRead)
async def add_support_case_message_route(
    case_id: UUID,
    payload: SupportCaseMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await add_support_case_message_for_user(db, case_id=case_id, current_user=current_user, body=payload.body)


@router.post("/{case_id}/attachments", response_model=SupportCaseDetailRead)
async def add_support_case_attachment_route(
    case_id: UUID,
    payload: SupportCaseAttachmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await add_support_case_attachment_for_user(
        db,
        case_id=case_id,
        current_user=current_user,
        file_name=payload.file_name,
        storage_key=payload.storage_key,
        file_mime_type=payload.file_mime_type,
        file_size_bytes=payload.file_size_bytes,
        checksum_sha256=payload.checksum_sha256,
    )


@router.post("/{case_id}/status", response_model=SupportCaseDetailRead)
async def update_support_case_status_route(
    case_id: UUID,
    payload: SupportCaseUserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_support_case_status_for_user(
        db,
        case_id=case_id,
        current_user=current_user,
        action=payload.action,
        message=payload.message,
    )

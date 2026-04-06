from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.schemas.support_cases import (
    SupportCaseAdminAssign,
    SupportCaseAttachmentCreate,
    SupportCaseAdminStatusUpdate,
    SupportCaseDetailRead,
    SupportCaseMessageCreate,
    SupportCaseRead,
)
from app.services.support_case_service import (
    add_support_case_attachment_admin,
    assign_support_case_admin,
    get_support_case_detail_admin,
    list_support_cases_admin,
    reply_support_case_admin,
    update_support_case_status_admin,
)

router = APIRouter(prefix="/admin/support-cases", tags=["Admin Support Cases"])


@router.get("", response_model=list[SupportCaseRead])
async def list_support_cases_admin_route(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    return await list_support_cases_admin(db, status=status, q=q, limit=limit)


@router.get("/{case_id}", response_model=SupportCaseDetailRead)
async def get_support_case_detail_admin_route(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    return await get_support_case_detail_admin(db, case_id=case_id)


@router.post("/{case_id}/assign", response_model=SupportCaseDetailRead)
async def assign_support_case_admin_route(
    case_id: UUID,
    payload: SupportCaseAdminAssign,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    return await assign_support_case_admin(
        db,
        case_id=case_id,
        admin_user=admin,
        assigned_to_user_id=payload.assigned_to_user_id,
    )


@router.post("/{case_id}/status", response_model=SupportCaseDetailRead)
async def update_support_case_status_admin_route(
    case_id: UUID,
    payload: SupportCaseAdminStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    return await update_support_case_status_admin(
        db,
        case_id=case_id,
        admin_user=admin,
        status=payload.status,
        resolution_code=payload.resolution_code,
        reason_code=payload.reason_code,
        message=payload.message,
    )


@router.post("/{case_id}/reply", response_model=SupportCaseDetailRead)
async def reply_support_case_admin_route(
    case_id: UUID,
    payload: SupportCaseMessageCreate,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    return await reply_support_case_admin(db, case_id=case_id, admin_user=admin, body=payload.body)


@router.post("/{case_id}/attachments", response_model=SupportCaseDetailRead)
async def add_support_case_attachment_admin_route(
    case_id: UUID,
    payload: SupportCaseAttachmentCreate,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    return await add_support_case_attachment_admin(
        db,
        case_id=case_id,
        admin_user=admin,
        file_name=payload.file_name,
        storage_key=payload.storage_key,
        file_mime_type=payload.file_mime_type,
        file_size_bytes=payload.file_size_bytes,
        checksum_sha256=payload.checksum_sha256,
    )

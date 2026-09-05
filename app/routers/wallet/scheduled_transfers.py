from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db
from app.models.scheduled_transfers import ScheduledTransfers
from app.models.users import Users
from app.schemas.scheduled_transfers import ScheduledTransferCreate, ScheduledTransferRead, ScheduledTransferUpdate
from app.services.scheduled_transfer_service import (
    cancel_scheduled_transfer,
    create_scheduled_transfer,
    get_scheduled_transfer_diagnostic,
    list_scheduled_transfers,
    pause_scheduled_transfer,
    resume_scheduled_transfer,
    run_due_scheduled_transfers,
    run_scheduled_transfer_now,
    update_scheduled_transfer,
)

router = APIRouter(tags=["Scheduled Transfers"])


@router.get("/admin/scheduled-transfers")
async def list_admin_scheduled_transfers(
    transfer_type: str | None = Query(None, pattern="^(internal|external)$"),
    status: str | None = Query(None, pattern="^(active|paused|cancelled|completed|failed)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = select(ScheduledTransfers).order_by(ScheduledTransfers.updated_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(ScheduledTransfers.status == status)
    if transfer_type:
        stmt = stmt.where(ScheduledTransfers.metadata_["transfer_type"].astext == transfer_type)
    rows = (await db.execute(stmt)).scalars().all()
    items = []
    for item in rows:
        metadata = dict(item.metadata_ or {})
        item_type = "external" if metadata.get("transfer_type") == "external" else "internal"
        items.append(
            {
                "schedule_id": str(item.schedule_id),
                "user_id": str(item.user_id),
                "transfer_type": item_type,
                "receiver_identifier": item.receiver_identifier,
                "amount": str(item.amount),
                "currency_code": item.currency_code,
                "frequency": item.frequency,
                "status": item.status,
                "last_result": item.last_result,
                "failure_count": int(metadata.get("failure_count") or 0),
                "next_run_at": item.next_run_at,
                "last_run_at": item.last_run_at,
                "updated_at": item.updated_at,
            }
        )
    return items


@router.get("/wallet/scheduled-transfers", response_model=list[ScheduledTransferRead])
async def list_scheduled_transfers_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_scheduled_transfers(db, current_user=current_user)


@router.get("/wallet/scheduled-transfers/{schedule_id}/diagnostic")
async def get_scheduled_transfer_diagnostic_route(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_scheduled_transfer_diagnostic(
        db,
        current_user=current_user,
        schedule_id=schedule_id,
    )


@router.post("/wallet/scheduled-transfers", response_model=ScheduledTransferRead)
async def create_scheduled_transfer_route(
    payload: ScheduledTransferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_scheduled_transfer(db, current_user=current_user, payload=payload)


@router.put("/wallet/scheduled-transfers/{schedule_id}", response_model=ScheduledTransferRead)
async def update_scheduled_transfer_route(
    schedule_id: UUID,
    payload: ScheduledTransferUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_scheduled_transfer(
        db,
        current_user=current_user,
        schedule_id=schedule_id,
        payload=payload,
    )


@router.post("/wallet/scheduled-transfers/run-due", response_model=list[ScheduledTransferRead])
async def run_due_scheduled_transfers_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await run_due_scheduled_transfers(db, current_user=current_user)


@router.post("/wallet/scheduled-transfers/{schedule_id}/run", response_model=ScheduledTransferRead)
async def run_scheduled_transfer_now_route(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await run_scheduled_transfer_now(db, current_user=current_user, schedule_id=schedule_id)


@router.post("/wallet/scheduled-transfers/{schedule_id}/cancel", response_model=ScheduledTransferRead)
async def cancel_scheduled_transfer_route(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await cancel_scheduled_transfer(db, current_user=current_user, schedule_id=schedule_id)


@router.post("/wallet/scheduled-transfers/{schedule_id}/pause", response_model=ScheduledTransferRead)
async def pause_scheduled_transfer_route(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await pause_scheduled_transfer(db, current_user=current_user, schedule_id=schedule_id)


@router.post("/wallet/scheduled-transfers/{schedule_id}/resume", response_model=ScheduledTransferRead)
async def resume_scheduled_transfer_route(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await resume_scheduled_transfer(db, current_user=current_user, schedule_id=schedule_id)

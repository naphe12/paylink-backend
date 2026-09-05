from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db
from app.models.scheduled_transfers import ScheduledTransfers
from app.models.users import Users
from app.schemas.scheduled_transfers import ScheduledTransferCreate, ScheduledTransferRead, ScheduledTransferUpdate
from app.services.scheduled_transfers_runtime_schema import ensure_scheduled_transfers_schema
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


@router.get("/admin/scheduled-transfer-executions")
async def list_admin_scheduled_transfer_executions(
    transfer_type: str | None = Query(None, pattern="^(internal|external)$"),
    outcome: str | None = Query(None, pattern="^(succeeded|failed)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    execution_log_table = await db.scalar(
        text("SELECT to_regclass('product_transfers.scheduled_transfer_execution_logs')")
    )
    if execution_log_table is None:
        await ensure_scheduled_transfers_schema(db)

    clauses, params = [], {"limit": limit, "offset": offset}
    if transfer_type:
        clauses.append("transfer_type = :transfer_type")
        params["transfer_type"] = transfer_type
    if outcome:
        clauses.append("outcome = :outcome")
        params["outcome"] = outcome
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = (await db.execute(text(f"""
        SELECT execution_id, schedule_id, user_id, transfer_type, outcome, schedule_status,
               amount, currency_code, reason, error_type, stack_trace, duration_ms, details, created_at
        FROM product_transfers.scheduled_transfer_execution_logs
        {where_sql}
        ORDER BY created_at DESC LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    return [
        {
            **dict(row),
            "execution_id": str(row["execution_id"]),
            "schedule_id": str(row["schedule_id"]),
            "user_id": str(row["user_id"]),
            "amount": str(row["amount"]),
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


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


@router.get("/wallet/internal-transfer-recipients/search")
async def search_scheduled_transfer_recipients(
    query: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    term = query.strip().lower()
    if len(term) < 2:
        return []

    prefix = f"{term}%"
    paytag_prefix = prefix if term.startswith("@") else f"@{prefix}"
    rows = (
        await db.execute(
            select(
                Users.user_id,
                Users.full_name,
                Users.username,
                Users.email,
                Users.phone_e164,
                Users.paytag,
            )
            .where(
                Users.user_id != current_user.user_id,
                or_(
                    func.lower(func.coalesce(Users.full_name, "")).like(prefix),
                    func.lower(func.coalesce(Users.username, "")).like(prefix),
                    func.lower(func.coalesce(Users.email, "")).like(prefix),
                    func.lower(func.coalesce(Users.phone_e164, "")).like(prefix),
                    func.lower(func.coalesce(Users.paytag, "")).like(paytag_prefix),
                ),
            )
            .order_by(Users.full_name.asc(), Users.email.asc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "user_id": str(row.user_id),
            "full_name": row.full_name,
            "username": row.username,
            "email": row.email,
            "phone": row.phone_e164,
            "paytag": row.paytag,
        }
        for row in rows
    ]


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

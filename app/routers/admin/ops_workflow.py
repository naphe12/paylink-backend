from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.dependencies.step_up import require_admin_step_up
from app.models.users import Users
from app.schemas.operator_workflow import (
    OperatorUrgencyListRead,
    OperatorWorkflowBatchResultRead,
    OperatorWorkflowBatchUpsert,
    OperatorWorkflowRead,
    OperatorWorkflowSummaryRead,
    OperatorWorkflowUpsert,
)
from app.services.operator_workflow_service import (
    fetch_operator_urgency_items,
    fetch_operator_work_item,
    fetch_operator_workflow_summary,
    filter_operator_urgency_items,
    paginate_operator_urgency_items,
    sort_operator_urgency_items,
    summarize_operator_urgency_owner_load,
    summarize_operator_urgency_queues,
    upsert_operator_work_item,
)


router = APIRouter(prefix="/admin/ops/work-items", tags=["Admin OPS Workflow"])

ALLOWED_ENTITY_TYPES = {"escrow_order", "p2p_dispute", "payment_intent"}


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def _ensure_entity_exists(db: AsyncSession, *, entity_type: str, entity_id: str) -> None:
    lookup = {
        "escrow_order": "SELECT 1 FROM escrow.orders WHERE id = CAST(:entity_id AS uuid) LIMIT 1",
        "p2p_dispute": "SELECT 1 FROM p2p.disputes WHERE dispute_id = CAST(:entity_id AS uuid) LIMIT 1",
        "payment_intent": "SELECT 1 FROM paylink.payment_intents WHERE intent_id = CAST(:entity_id AS uuid) LIMIT 1",
    }
    sql = lookup.get(entity_type)
    if not sql:
        raise HTTPException(status_code=400, detail="entity_type non supporte.")
    row = await db.execute(text(sql), {"entity_id": entity_id})
    if row.first() is None:
        raise HTTPException(status_code=404, detail="Entity introuvable pour ce workflow operateur.")


@router.get("/summary", response_model=OperatorWorkflowSummaryRead)
async def get_operator_workflow_summary(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_admin),
):
    return await fetch_operator_workflow_summary(
        db,
        current_user_id=str(current_user.user_id),
        current_owner_label=getattr(current_user, "full_name", None) or getattr(current_user, "email", None),
    )


@router.get("/urgencies", response_model=OperatorUrgencyListRead)
async def get_operator_urgency_items(
    kind: str | None = Query(None),
    operator_status: str | None = Query(None),
    owner_key: str | None = Query(None),
    view: str | None = Query(None),
    q: str | None = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("last_action_at"),
    sort_dir: str = Query("desc"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_admin),
):
    items = await fetch_operator_urgency_items(db)
    filtered = filter_operator_urgency_items(
        items,
        kind=kind,
        operator_status=operator_status,
        owner_key=owner_key,
        view=view,
        q=q,
        current_user_id=str(current_user.user_id),
        current_owner_label=getattr(current_user, "full_name", None) or getattr(current_user, "email", None),
    )
    if overdue_only:
        filtered = [
            item
            for item in filtered
            if (item.get("operator_workflow") or {}).get("follow_up_at")
            and (_parse_dt((item.get("operator_workflow") or {}).get("follow_up_at")) or datetime.max.replace(tzinfo=timezone.utc))
            <= datetime.now(timezone.utc)
        ]
    owner_load = summarize_operator_urgency_owner_load(filtered)
    queue_summary = summarize_operator_urgency_queues(filtered)
    sorted_items = sort_operator_urgency_items(filtered, sort_by=sort_by, sort_dir=sort_dir)
    paginated = paginate_operator_urgency_items(sorted_items, limit=limit, offset=offset)
    return {
        "items": paginated,
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "owner_load": owner_load,
        "queue_summary": queue_summary,
    }


@router.get("/{entity_type}/{entity_id}", response_model=OperatorWorkflowRead | None)
async def get_operator_work_item(
    entity_type: str,
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    normalized = str(entity_type).strip().lower()
    if normalized not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="entity_type non supporte.")
    return await fetch_operator_work_item(
        db,
        entity_type=normalized,
        entity_id=str(entity_id),
    )


@router.put(
    "/{entity_type}/{entity_id}",
    response_model=OperatorWorkflowRead,
    dependencies=[Depends(require_admin_step_up("admin_write"))],
)
async def put_operator_work_item(
    entity_type: str,
    entity_id: UUID,
    payload: OperatorWorkflowUpsert,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    normalized = str(entity_type).strip().lower()
    if normalized not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="entity_type non supporte.")

    await _ensure_entity_exists(db, entity_type=normalized, entity_id=str(entity_id))
    changes = payload.model_dump(exclude_unset=True)
    result = await upsert_operator_work_item(
        db,
        entity_type=normalized,
        entity_id=str(entity_id),
        changes=changes,
    )
    await db.commit()
    return result


@router.post(
    "/batch",
    response_model=OperatorWorkflowBatchResultRead,
    dependencies=[Depends(require_admin_step_up("admin_write"))],
)
async def batch_upsert_operator_work_items(
    payload: OperatorWorkflowBatchUpsert,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    changes = payload.model_dump(exclude_unset=True, exclude={"targets"})
    results = []
    for target in payload.targets:
        normalized = str(target.entity_type).strip().lower()
        if normalized not in ALLOWED_ENTITY_TYPES:
            raise HTTPException(status_code=400, detail="entity_type non supporte.")
        await _ensure_entity_exists(db, entity_type=normalized, entity_id=str(target.entity_id))
        result = await upsert_operator_work_item(
            db,
            entity_type=normalized,
            entity_id=str(target.entity_id),
            changes=changes,
        )
        results.append(result)
    await db.commit()
    return {"updated": len(results), "items": results}

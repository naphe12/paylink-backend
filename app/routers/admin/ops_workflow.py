from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.schemas.operator_workflow import (
    OperatorUrgencyItemRead,
    OperatorWorkflowRead,
    OperatorWorkflowSummaryRead,
    OperatorWorkflowUpsert,
)
from app.services.operator_workflow_service import (
    fetch_operator_urgency_items,
    fetch_operator_work_item,
    fetch_operator_workflow_summary,
    filter_operator_urgency_items,
    upsert_operator_work_item,
)


router = APIRouter(prefix="/admin/ops/work-items", tags=["Admin OPS Workflow"])

ALLOWED_ENTITY_TYPES = {"escrow_order", "p2p_dispute", "payment_intent"}


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


@router.get("/urgencies", response_model=list[OperatorUrgencyItemRead])
async def get_operator_urgency_items(
    kind: str | None = Query(None),
    operator_status: str | None = Query(None),
    owner_key: str | None = Query(None),
    view: str | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_admin),
):
    items = await fetch_operator_urgency_items(db)
    return filter_operator_urgency_items(
        items,
        kind=kind,
        operator_status=operator_status,
        owner_key=owner_key,
        view=view,
        q=q,
        current_user_id=str(current_user.user_id),
        current_owner_label=getattr(current_user, "full_name", None) or getattr(current_user, "email", None),
    )


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


@router.put("/{entity_type}/{entity_id}", response_model=OperatorWorkflowRead)
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

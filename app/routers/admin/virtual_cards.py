from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.dependencies.step_up import require_admin_step_up
from app.models.users import Users
from app.schemas.virtual_cards import VirtualCardAdminRead, VirtualCardControlsUpdate, VirtualCardStatusUpdate
from app.services.virtual_cards_service import (
    get_admin_virtual_card_detail,
    list_admin_virtual_cards,
    update_admin_virtual_card_controls,
    update_admin_virtual_card_status,
)

router = APIRouter(prefix="/admin/virtual-cards", tags=["Admin Virtual Cards"])


@router.get("", response_model=list[VirtualCardAdminRead])
async def list_admin_virtual_cards_route(
    status: str | None = Query(default=None),
    card_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    return await list_admin_virtual_cards(db, status=status, card_type=card_type, q=q, limit=limit)


@router.get("/{card_id}", response_model=VirtualCardAdminRead)
async def get_admin_virtual_card_detail_route(
    card_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    return await get_admin_virtual_card_detail(db, card_id=card_id)


@router.post(
    "/{card_id}/status",
    response_model=VirtualCardAdminRead,
    dependencies=[Depends(require_admin_step_up("admin_write"))],
)
async def update_admin_virtual_card_status_route(
    card_id: UUID,
    payload: VirtualCardStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: Users = Depends(get_current_admin),
):
    return await update_admin_virtual_card_status(db, card_id=card_id, payload=payload, current_admin=current_admin)


@router.put(
    "/{card_id}/controls",
    response_model=VirtualCardAdminRead,
    dependencies=[Depends(require_admin_step_up("admin_write"))],
)
async def update_admin_virtual_card_controls_route(
    card_id: UUID,
    payload: VirtualCardControlsUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: Users = Depends(get_current_admin),
):
    return await update_admin_virtual_card_controls(db, card_id=card_id, payload=payload, current_admin=current_admin)

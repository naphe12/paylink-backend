from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.virtual_cards import (
    VirtualCardChargeCreate,
    VirtualCardControlsUpdate,
    VirtualCardCreate,
    VirtualCardRead,
    VirtualCardStatusUpdate,
)
from app.services.virtual_cards_service import (
    charge_virtual_card,
    create_virtual_card,
    get_virtual_card_detail,
    list_virtual_cards,
    update_virtual_card_controls,
    update_virtual_card_status,
)

router = APIRouter(tags=["Virtual Cards"])


@router.get("/virtual-cards", response_model=list[VirtualCardRead])
async def list_virtual_cards_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_virtual_cards(db, current_user=current_user)


@router.post("/virtual-cards", response_model=VirtualCardRead)
async def create_virtual_card_route(
    payload: VirtualCardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_virtual_card(db, current_user=current_user, payload=payload)


@router.get("/virtual-cards/{card_id}", response_model=VirtualCardRead)
async def get_virtual_card_detail_route(
    card_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_virtual_card_detail(db, current_user=current_user, card_id=card_id)


@router.post("/virtual-cards/{card_id}/status", response_model=VirtualCardRead)
async def update_virtual_card_status_route(
    card_id: UUID,
    payload: VirtualCardStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_virtual_card_status(db, current_user=current_user, card_id=card_id, payload=payload)


@router.put("/virtual-cards/{card_id}/controls", response_model=VirtualCardRead)
async def update_virtual_card_controls_route(
    card_id: UUID,
    payload: VirtualCardControlsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_virtual_card_controls(db, current_user=current_user, card_id=card_id, payload=payload)


@router.post("/virtual-cards/{card_id}/charge", response_model=VirtualCardRead)
async def charge_virtual_card_route(
    card_id: UUID,
    payload: VirtualCardChargeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await charge_virtual_card(db, current_user=current_user, card_id=card_id, payload=payload)

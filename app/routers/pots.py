from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.pots import PotContributionCreate, PotCreate, PotMemberCreate, PotMemberUpdate, PotRead
from app.services.pots_service import (
    add_pot_member,
    close_pot,
    contribute_pot,
    create_pot,
    get_pot_detail,
    leave_pot,
    list_my_pots,
    update_pot_member,
)

router = APIRouter(tags=["Pots"])


@router.get("/pots", response_model=list[PotRead])
async def list_my_pots_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_my_pots(db, current_user=current_user)


@router.post("/pots", response_model=PotRead)
async def create_pot_route(
    payload: PotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_pot(db, current_user=current_user, payload=payload)


@router.get("/pots/{pot_id}", response_model=PotRead)
async def get_pot_detail_route(
    pot_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_pot_detail(db, current_user=current_user, pot_id=pot_id)


@router.post("/pots/{pot_id}/members", response_model=PotRead)
async def add_pot_member_route(
    pot_id: UUID,
    payload: PotMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await add_pot_member(db, current_user=current_user, pot_id=pot_id, payload=payload)


@router.put("/pots/{pot_id}/members/{membership_id}", response_model=PotRead)
async def update_pot_member_route(
    pot_id: UUID,
    membership_id: UUID,
    payload: PotMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_pot_member(
        db,
        current_user=current_user,
        pot_id=pot_id,
        membership_id=membership_id,
        payload=payload,
    )


@router.post("/pots/{pot_id}/contribute", response_model=PotRead)
async def contribute_pot_route(
    pot_id: UUID,
    payload: PotContributionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await contribute_pot(db, current_user=current_user, pot_id=pot_id, payload=payload)


@router.post("/pots/{pot_id}/leave")
async def leave_pot_route(
    pot_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await leave_pot(db, current_user=current_user, pot_id=pot_id)


@router.post("/pots/{pot_id}/close", response_model=PotRead)
async def close_pot_route(
    pot_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await close_pot(db, current_user=current_user, pot_id=pot_id)

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db
from app.models.users import Users
from app.schemas.trust import TrustProfileDetailRead
from app.services.trust_service_v2 import get_trust_profile, recompute_trust_profile

router = APIRouter(tags=["Trust"])


@router.get("/trust/me", response_model=TrustProfileDetailRead)
async def get_my_trust_profile_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_trust_profile(db, user_id=current_user.user_id)


@router.get("/trust/users/{user_id}", response_model=TrustProfileDetailRead)
async def get_user_trust_profile_route(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    return await get_trust_profile(db, user_id=user_id)


@router.post("/admin/trust/recompute/{user_id}", response_model=TrustProfileDetailRead)
async def recompute_user_trust_profile_route(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(get_current_admin),
):
    profile = await recompute_trust_profile(db, user_id=user_id)
    detail = await get_trust_profile(db, user_id=user_id)
    detail["profile"] = profile
    return detail

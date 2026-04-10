from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.referrals import ReferralApplyCode, ReferralProfileRead
from app.services.referral_service import (
    activate_referral_if_eligible,
    apply_referral_code,
    get_my_referral_profile,
)

router = APIRouter(tags=["Referrals"])


@router.get("/referrals/me", response_model=ReferralProfileRead)
async def get_my_referral_profile_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_my_referral_profile(db, current_user=current_user)


@router.post("/referrals/apply")
async def apply_referral_code_route(
    payload: ReferralApplyCode,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await apply_referral_code(db, current_user=current_user, referral_code=payload.referral_code)


@router.post("/referrals/activate")
async def activate_referral_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await activate_referral_if_eligible(db, current_user=current_user)

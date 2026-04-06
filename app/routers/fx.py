from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.fx import CurrencyPreferenceRead, CurrencyPreferenceUpdate, WalletDisplaySummaryRead
from app.services.fx_visibility_service import (
    get_user_display_currency_preference,
    get_wallet_display_summary,
    set_user_display_currency_preference,
)

router = APIRouter(tags=["FX Visibility"])


@router.get("/fx/preferences/me", response_model=CurrencyPreferenceRead)
async def get_my_display_currency_preference_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_user_display_currency_preference(db, user=current_user)


@router.put("/fx/preferences/me", response_model=CurrencyPreferenceRead)
async def update_my_display_currency_preference_route(
    payload: CurrencyPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    try:
        return await set_user_display_currency_preference(
            db,
            user=current_user,
            display_currency=payload.display_currency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wallet/balances", response_model=WalletDisplaySummaryRead)
async def get_wallet_balances_summary_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_wallet_display_summary(db, user=current_user)

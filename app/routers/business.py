from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.business_accounts import (
    BusinessAccountCreate,
    BusinessAccountRead,
    BusinessMemberCreate,
    BusinessMemberUpdate,
    BusinessSubWalletCreate,
    BusinessSubWalletMovementCreate,
    BusinessSubWalletUpdate,
)
from app.schemas.payment_requests import PaymentRequestAdminDetailRead, PaymentRequestAdminRead, PaymentRequestCreate
from app.services.business_service import (
    add_business_member,
    create_business_account,
    create_business_sub_wallet,
    fund_business_sub_wallet,
    list_my_business_accounts,
    release_business_sub_wallet,
    update_business_member,
    update_business_sub_wallet,
)
from app.services.payment_request_service import (
    create_business_payment_request,
    get_business_payment_request_detail,
    list_business_payment_requests,
)

router = APIRouter(tags=["Business Accounts"])


@router.get("/business-accounts", response_model=list[BusinessAccountRead])
async def list_my_business_accounts_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_my_business_accounts(db, current_user=current_user)


@router.post("/business-accounts", response_model=BusinessAccountRead)
async def create_business_account_route(
    payload: BusinessAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_business_account(db, current_user=current_user, payload=payload)


@router.post("/business-accounts/{business_id}/members", response_model=BusinessAccountRead)
async def add_business_member_route(
    business_id: UUID,
    payload: BusinessMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await add_business_member(db, current_user=current_user, business_id=business_id, payload=payload)


@router.put("/business-accounts/{business_id}/members/{membership_id}", response_model=BusinessAccountRead)
async def update_business_member_route(
    business_id: UUID,
    membership_id: UUID,
    payload: BusinessMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_business_member(
        db,
        current_user=current_user,
        business_id=business_id,
        membership_id=membership_id,
        payload=payload,
    )


@router.post("/business-accounts/{business_id}/sub-wallets", response_model=BusinessAccountRead)
async def create_business_sub_wallet_route(
    business_id: UUID,
    payload: BusinessSubWalletCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_business_sub_wallet(db, current_user=current_user, business_id=business_id, payload=payload)


@router.put("/business-sub-wallets/{sub_wallet_id}", response_model=BusinessAccountRead)
async def update_business_sub_wallet_route(
    sub_wallet_id: UUID,
    payload: BusinessSubWalletUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await update_business_sub_wallet(db, current_user=current_user, sub_wallet_id=sub_wallet_id, payload=payload)


@router.post("/business-sub-wallets/{sub_wallet_id}/fund", response_model=BusinessAccountRead)
async def fund_business_sub_wallet_route(
    sub_wallet_id: UUID,
    payload: BusinessSubWalletMovementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await fund_business_sub_wallet(db, current_user=current_user, sub_wallet_id=sub_wallet_id, payload=payload)


@router.post("/business-sub-wallets/{sub_wallet_id}/release", response_model=BusinessAccountRead)
async def release_business_sub_wallet_route(
    sub_wallet_id: UUID,
    payload: BusinessSubWalletMovementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await release_business_sub_wallet(db, current_user=current_user, sub_wallet_id=sub_wallet_id, payload=payload)


@router.get("/business-accounts/{business_id}/payment-requests", response_model=list[PaymentRequestAdminRead])
async def list_business_payment_requests_route(
    business_id: UUID,
    status: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_business_payment_requests(
        db,
        business_id=business_id,
        current_user=current_user,
        status=status,
        limit=limit,
    )


@router.post("/business-accounts/{business_id}/payment-requests", response_model=PaymentRequestAdminRead)
async def create_business_payment_request_route(
    business_id: UUID,
    payload: PaymentRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    request_obj = await create_business_payment_request(
        db,
        business_id=business_id,
        current_user=current_user,
        payload=payload,
    )
    items = await list_business_payment_requests(
        db,
        business_id=business_id,
        current_user=current_user,
        limit=200,
    )
    for item in items:
        if item["request_id"] == request_obj.request_id:
            return item
    raise RuntimeError(f"Business payment request {request_obj.request_id} not found in current view.")


@router.get("/business-accounts/{business_id}/payment-requests/{request_id}", response_model=PaymentRequestAdminDetailRead)
async def get_business_payment_request_detail_route(
    business_id: UUID,
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_business_payment_request_detail(
        db,
        business_id=business_id,
        request_id=request_id,
        current_user=current_user,
    )

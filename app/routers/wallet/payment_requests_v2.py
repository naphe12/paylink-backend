from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.users import Users
from app.schemas.payment_requests import (
    PaymentRequestAction,
    PaymentRequestAutoPayUpdate,
    PaymentRequestBatchRunRead,
    PaymentRequestCreate,
    PaymentRequestDetailRead,
    PaymentRequestRead,
)
from app.services.payment_request_service import (
    cancel_payment_request,
    create_payment_request,
    decline_payment_request,
    get_payment_request_detail,
    get_payment_request_public_view,
    list_payment_requests,
    pay_payment_request,
    remind_payment_request,
    run_due_payment_request_maintenance,
    update_payment_request_auto_pay,
)

router = APIRouter(prefix="/wallet/payment-requests", tags=["Wallet Payment Requests"])


def _find_request_or_fallback(items: list[dict], request_id: UUID) -> dict:
    request_id_str = str(request_id)
    for item in items:
        if str(item["request_id"]) == request_id_str:
            return item
    raise RuntimeError(f"Payment request {request_id} not found in current view.")


@router.post("", response_model=PaymentRequestRead)
async def create_payment_request_route(
    payload: PaymentRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    request_obj = await create_payment_request(db, current_user=current_user, payload=payload)
    items = await list_payment_requests(db, current_user=current_user)
    return _find_request_or_fallback(items, request_obj.request_id)


@router.get("", response_model=list[PaymentRequestRead])
async def list_payment_requests_route(
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await list_payment_requests(db, current_user=current_user, status=status)


@router.get("/share/{share_token}", response_model=PaymentRequestRead)
async def get_payment_request_by_share_token_route(
    share_token: str,
    db: AsyncSession = Depends(get_db),
):
    return await get_payment_request_public_view(db, share_token)


@router.get("/{request_id}", response_model=PaymentRequestDetailRead)
async def get_payment_request_detail_route(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await get_payment_request_detail(db, request_id=request_id, current_user=current_user)


@router.post("/{request_id}/pay", response_model=PaymentRequestRead)
async def pay_payment_request_route(
    request_id: UUID,
    payload: PaymentRequestAction,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    request_obj = await pay_payment_request(db, request_id=request_id, current_user=current_user, reason=payload.reason)
    items = await list_payment_requests(db, current_user=current_user)
    return _find_request_or_fallback(items, request_obj.request_id)


@router.post("/{request_id}/decline", response_model=PaymentRequestRead)
async def decline_payment_request_route(
    request_id: UUID,
    payload: PaymentRequestAction,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    request_obj = await decline_payment_request(db, request_id=request_id, current_user=current_user, reason=payload.reason)
    items = await list_payment_requests(db, current_user=current_user)
    return _find_request_or_fallback(items, request_obj.request_id)


@router.post("/{request_id}/cancel", response_model=PaymentRequestRead)
async def cancel_payment_request_route(
    request_id: UUID,
    payload: PaymentRequestAction,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    request_obj = await cancel_payment_request(db, request_id=request_id, current_user=current_user, reason=payload.reason)
    items = await list_payment_requests(db, current_user=current_user)
    return _find_request_or_fallback(items, request_obj.request_id)


@router.post("/{request_id}/remind", response_model=PaymentRequestRead)
async def remind_payment_request_route(
    request_id: UUID,
    payload: PaymentRequestAction,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    request_obj = await remind_payment_request(db, request_id=request_id, current_user=current_user, reason=payload.reason)
    items = await list_payment_requests(db, current_user=current_user)
    return _find_request_or_fallback(items, request_obj.request_id)


@router.post("/{request_id}/autopay", response_model=PaymentRequestRead)
async def update_payment_request_autopay_route(
    request_id: UUID,
    payload: PaymentRequestAutoPayUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    request_obj = await update_payment_request_auto_pay(
        db,
        request_id=request_id,
        current_user=current_user,
        enabled=payload.enabled,
        max_amount=payload.max_amount,
        reason=payload.reason,
    )
    items = await list_payment_requests(db, current_user=current_user)
    return _find_request_or_fallback(items, request_obj.request_id)


@router.post("/run-due", response_model=PaymentRequestBatchRunRead)
async def run_due_payment_requests_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    return await run_due_payment_request_maintenance(db, current_user=current_user)

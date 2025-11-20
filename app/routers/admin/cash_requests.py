import decimal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.models.wallet_cash_requests import (
    WalletCashRequestStatus,
    WalletCashRequestType,
    WalletCashRequests,
)
from app.models.wallets import Wallets
from app.schemas.wallet_cash_requests import (
    WalletCashDecision,
    WalletCashRequestAdminRead,
    WalletCashRequestRead,
)
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement

router = APIRouter(prefix="/admin/cash-requests", tags=["Admin Cash Requests"])


async def _serialize_request(
    db: AsyncSession, request: WalletCashRequests
) -> WalletCashRequestAdminRead:
    user = await db.get(Users, request.user_id)
    base = WalletCashRequestRead.model_validate(request)
    return WalletCashRequestAdminRead(
        **base.model_dump(),
        user={
            "user_id": request.user_id,
            "full_name": getattr(user, "full_name", None),
            "email": getattr(user, "email", None),
        },
    )


@router.get("/", response_model=list[WalletCashRequestAdminRead])
async def list_cash_requests(
    status: WalletCashRequestStatus | None = Query(None),
    request_type: WalletCashRequestType | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(WalletCashRequests)
        .where(True)
        .order_by(WalletCashRequests.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(WalletCashRequests.status == status)
    if request_type:
        stmt = stmt.where(WalletCashRequests.type == request_type)

    requests = (await db.execute(stmt)).scalars().all()
    return [await _serialize_request(db, req) for req in requests]


@router.post("/{request_id}/approve", response_model=WalletCashRequestAdminRead)
async def approve_cash_request(
    request_id: UUID,
    payload: WalletCashDecision,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    request = await db.get(WalletCashRequests, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if request.status != WalletCashRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Demande déjà traitée")

    wallet = await db.get(Wallets, request.wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable")

    ledger = LedgerService(db)
    movement = None
    metadata = {
        "cash_request_id": str(request.request_id),
        "processed_by": str(admin.user_id),
        "type": request.type.value,
    }

    if request.type == WalletCashRequestType.DEPOSIT:
        wallet.available += request.amount
        movement = await log_wallet_movement(
            db,
            wallet=wallet,
            user_id=wallet.user_id,
            amount=request.amount,
            direction="credit",
            operation_type="cash_deposit_admin",
            reference="cash_deposit",
            description="Validation dépôt cash",
        )
        wallet_account = await ledger.ensure_wallet_account(wallet)
        cash_in = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CASH_IN)
        await ledger.post_journal(
            tx_id=None,
            description="Validation dépôt cash",
            metadata=metadata
            | ({"movement_id": str(movement.transaction_id)} if movement else {}),
            entries=[
                LedgerLine(
                    account=cash_in,
                    direction="debit",
                    amount=request.amount,
                    currency_code=wallet.currency_code,
                ),
                LedgerLine(
                    account=wallet_account,
                    direction="credit",
                    amount=request.amount,
                    currency_code=wallet.currency_code,
                ),
            ],
        )
    else:
        total = decimal.Decimal(request.total_amount or 0)
        if wallet.available < total:
            raise HTTPException(
                status_code=400,
                detail="Solde insuffisant pour approuver ce retrait",
            )
        wallet.available -= total
        movement = await log_wallet_movement(
            db,
            wallet=wallet,
            user_id=wallet.user_id,
            amount=total,
            direction="debit",
            operation_type="cash_withdraw_admin",
            reference=request.provider_name or request.mobile_number,
            description="Validation retrait cash",
        )
        wallet_account = await ledger.ensure_wallet_account(wallet)
        cash_out = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CASH_OUT)
        await ledger.post_journal(
            tx_id=None,
            description="Validation retrait cash",
            metadata=metadata
            | ({"movement_id": str(movement.transaction_id)} if movement else {}),
            entries=[
                LedgerLine(
                    account=wallet_account,
                    direction="debit",
                    amount=total,
                    currency_code=wallet.currency_code,
                ),
                LedgerLine(
                    account=cash_out,
                    direction="credit",
                    amount=total,
                    currency_code=wallet.currency_code,
                ),
            ],
        )

    request.status = WalletCashRequestStatus.APPROVED
    request.admin_note = payload.note
    request.processed_by = admin.user_id
    request.processed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(request)
    return await _serialize_request(db, request)


@router.post("/{request_id}/reject", response_model=WalletCashRequestAdminRead)
async def reject_cash_request(
    request_id: UUID,
    payload: WalletCashDecision,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    request = await db.get(WalletCashRequests, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if request.status != WalletCashRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Demande déjà traitée")

    request.status = WalletCashRequestStatus.REJECTED
    request.admin_note = payload.note
    request.processed_by = admin.user_id
    request.processed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(request)
    return await _serialize_request(db, request)

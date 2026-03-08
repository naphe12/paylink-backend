import decimal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
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


class AdminCashDepositCreate(BaseModel):
    user_id: UUID
    amount: decimal.Decimal = Field(gt=decimal.Decimal("0"))
    note: str | None = None


class AdminCashUserRead(BaseModel):
    user_id: UUID
    full_name: str | None = None
    email: str | None = None
    phone_e164: str | None = None


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


# Autorise /admin/cash-requests et /admin/cash-requests/
@router.get("", response_model=list[WalletCashRequestAdminRead])
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


@router.get("/users", response_model=list[AdminCashUserRead])
async def list_cash_users(
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = select(Users).order_by(Users.created_at.desc()).limit(limit)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = (
            select(Users)
            .where(
                (Users.full_name.ilike(pattern))
                | (Users.email.ilike(pattern))
                | (Users.phone_e164.ilike(pattern))
            )
            .order_by(Users.created_at.desc())
            .limit(limit)
        )
    users = (await db.execute(stmt)).scalars().all()
    return [
        AdminCashUserRead(
            user_id=u.user_id,
            full_name=u.full_name,
            email=u.email,
            phone_e164=u.phone_e164,
        )
        for u in users
    ]


@router.post("/deposit")
async def admin_cash_deposit_direct(
    payload: AdminCashDepositCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = await db.get(Users, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    wallet = await db.scalar(
        select(Wallets).where(
            Wallets.user_id == payload.user_id,
            Wallets.type == "consumer",
        )
    )
    if not wallet:
        wallet = await db.scalar(select(Wallets).where(Wallets.user_id == payload.user_id))
    if not wallet:
        wallet = Wallets(
            user_id=payload.user_id,
            type="consumer",
            currency_code="EUR",
            available=decimal.Decimal("0"),
            pending=decimal.Decimal("0"),
        )
        db.add(wallet)
        await db.flush()

    ledger = LedgerService(db)
    amount = decimal.Decimal(payload.amount)
    wallet.available = decimal.Decimal(wallet.available or 0) + amount
    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=user.user_id,
        amount=amount,
        direction="credit",
        operation_type="cash_deposit_admin_direct",
        reference=str(admin.user_id),
        description=f"Depot cash direct admin ({payload.note or 'sans note'})",
    )
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_in = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CASH_IN)
    await ledger.post_journal(
        tx_id=None,
        description="Depot cash direct admin",
        metadata={
            "operation": "cash_deposit_admin_direct",
            "target_user_id": str(user.user_id),
            "wallet_id": str(wallet.wallet_id),
            "processed_by": str(admin.user_id),
            "note": payload.note,
            "movement_id": str(movement.transaction_id) if movement else None,
        },
        entries=[
            LedgerLine(
                account=cash_in,
                direction="debit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
            LedgerLine(
                account=wallet_account,
                direction="credit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
        ],
    )
    await db.commit()
    return {
        "message": "Depot cash effectue",
        "user_id": str(user.user_id),
        "wallet_id": str(wallet.wallet_id),
        "amount": float(amount),
        "currency": wallet.currency_code,
        "new_balance": float(wallet.available),
    }


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

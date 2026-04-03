import decimal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import Integer, String, bindparam, cast, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.models.wallet_cash_requests import (
    WalletCashRequestStatus,
    WalletCashRequestType,
    WalletCashRequests,
    normalize_wallet_cash_request_status,
    normalize_wallet_cash_request_type,
)
from app.models.wallets import Wallets
from app.schemas.wallet_cash_requests import (
    WalletCashDecision,
    WalletCashRequestAdminRead,
    WalletCashRequestRead,
)
from app.services.idempotency_service import (
    acquire_idempotency,
    compute_request_hash,
    store_idempotency_response,
)
from app.services.cash_credit_recovery import (
    apply_cash_deposit_with_credit_recovery,
    apply_cash_withdraw_with_credit_usage,
)
from app.services.cash_request_rules import transition_cash_request_status
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement

router = APIRouter(prefix="/admin/cash-requests", tags=["Admin Cash Requests"])


def _build_cash_request_reference(request_id, request_type) -> str:
    type_token = str(getattr(request_type, "value", request_type) or "").strip().upper()
    prefix = {
        "DEPOSIT": "DEP",
        "WITHDRAW": "WDR",
        "EXTERNAL_TRANSFER": "EXT",
    }.get(type_token, "CSH")
    raw = str(request_id or "").replace("-", "").upper()
    return f"{prefix}-{raw[:10]}"


def _default_admin_cash_note(action: str, request_type: WalletCashRequestType | str | None = None) -> str:
    normalized_type = str(getattr(request_type, "value", request_type) or "").strip().lower()
    human_type = "cash in" if normalized_type == "deposit" else "cash out" if normalized_type == "withdraw" else "cash"
    label = {
        "direct_deposit": "Enregistrement admin",
        "approve": "Validation admin",
        "reject": "Rejet admin",
    }.get(action, "Action admin")
    return f"{label} {human_type}"


class AdminCashDepositCreate(BaseModel):
    user_id: UUID
    amount: decimal.Decimal = Field(gt=decimal.Decimal("0"))
    note: str | None = None


class AdminCashUserRead(BaseModel):
    user_id: UUID
    full_name: str | None = None
    email: str | None = None
    phone_e164: str | None = None


class AdminCashDepositSearchRead(BaseModel):
    deposit_created_at: datetime
    user_id: UUID
    user_full_name: str | None = None
    user_email: str | None = None
    wallet_id: UUID | None = None
    amount: decimal.Decimal
    currency_code: str
    operation_type: str
    deposit_mode: str
    new_balance: decimal.Decimal | None = None
    cash_request_id: UUID | None = None
    movement_id: UUID | None = None
    reference: str | None = None
    description: str | None = None
    admin_note: str | None = None
    admin_user_id: UUID | None = None
    admin_full_name: str | None = None
    admin_email: str | None = None


async def _serialize_request(
    db: AsyncSession, request: WalletCashRequests
) -> WalletCashRequestAdminRead:
    user = await db.get(Users, request.user_id)
    processor = await db.get(Users, request.processed_by) if request.processed_by else None
    base = WalletCashRequestRead.model_validate(request)
    return WalletCashRequestAdminRead(
        **base.model_dump(),
        reference_code=_build_cash_request_reference(request.request_id, request.type),
        user={
            "user_id": request.user_id,
            "full_name": getattr(user, "full_name", None),
            "email": getattr(user, "email", None),
        },
        processed_by_admin=(
            {
                "user_id": request.processed_by,
                "full_name": getattr(processor, "full_name", None),
                "email": getattr(processor, "email", None),
            }
            if processor
            else None
        ),
    )


async def _serialize_cash_request_row(
    db: AsyncSession,
    row,
) -> WalletCashRequestAdminRead | None:
    normalized_type = normalize_wallet_cash_request_type(row.type)
    normalized_status = normalize_wallet_cash_request_status(row.status)
    if not normalized_type or not normalized_status:
        return None
    user = await db.get(Users, row.user_id)
    processor = await db.get(Users, row.processed_by) if getattr(row, "processed_by", None) else None
    return WalletCashRequestAdminRead(
        request_id=row.request_id,
        reference_code=_build_cash_request_reference(row.request_id, normalized_type),
        type=normalized_type,
        status=normalized_status,
        amount=row.amount,
        fee_amount=row.fee_amount,
        total_amount=row.total_amount,
        currency_code=row.currency_code,
        mobile_number=row.mobile_number,
        provider_name=row.provider_name,
        note=row.note,
        admin_note=row.admin_note,
        created_at=row.created_at,
        processed_at=row.processed_at,
        user={
            "user_id": row.user_id,
            "full_name": getattr(user, "full_name", None),
            "email": getattr(user, "email", None),
        },
        processed_by_admin=(
            {
                "user_id": row.processed_by,
                "full_name": getattr(processor, "full_name", None),
                "email": getattr(processor, "email", None),
            }
            if processor
            else None
        ),
    )


# Autorise /admin/cash-requests et /admin/cash-requests/
@router.get("", response_model=list[WalletCashRequestAdminRead])
@router.get("/", response_model=list[WalletCashRequestAdminRead])
async def list_cash_requests(
    request: Request,
    status: str | None = Query(None),
    request_type: str | None = Query(None),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    normalized_status = normalize_wallet_cash_request_status(status) if status else None
    raw_type = request_type or request.query_params.get("type")
    normalized_type = normalize_wallet_cash_request_type(raw_type) if raw_type else None

    stmt = (
        select(
            WalletCashRequests.request_id,
            WalletCashRequests.user_id,
            cast(WalletCashRequests.type, String).label("type"),
            cast(WalletCashRequests.status, String).label("status"),
            WalletCashRequests.amount,
            WalletCashRequests.fee_amount,
            WalletCashRequests.total_amount,
            WalletCashRequests.currency_code,
            WalletCashRequests.mobile_number,
            WalletCashRequests.provider_name,
            WalletCashRequests.note,
            WalletCashRequests.admin_note,
            WalletCashRequests.created_at,
            WalletCashRequests.processed_at,
        )
        .where(True)
        .order_by(WalletCashRequests.created_at.desc())
        .limit(limit)
    )
    if normalized_status:
        stmt = stmt.where(cast(WalletCashRequests.status, String).in_([normalized_status.value, normalized_status.value.upper()]))
    if normalized_type:
        stmt = stmt.where(cast(WalletCashRequests.type, String).in_([normalized_type.value, normalized_type.value.lower()]))
    if created_from:
        stmt = stmt.where(WalletCashRequests.created_at >= created_from)
    if created_to:
        stmt = stmt.where(WalletCashRequests.created_at <= created_to)

    rows = (await db.execute(stmt)).all()
    result = []
    for row in rows:
        serialized = await _serialize_cash_request_row(db, row)
        if serialized is not None:
            result.append(serialized)
    return result


@router.get("/users", response_model=list[AdminCashUserRead])
async def list_cash_users(
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(Users)
        .where(Users.role == "client")
        .order_by(Users.created_at.desc())
        .limit(limit)
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = (
            select(Users)
            .where(
                (Users.role == "client")
                & (
                (Users.full_name.ilike(pattern))
                | (Users.email.ilike(pattern))
                | (Users.phone_e164.ilike(pattern))
                )
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


@router.get("/admin-deposits", response_model=list[AdminCashDepositSearchRead])
async def list_admin_cash_deposits(
    q: str | None = Query(None),
    user_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    params = {
        "user_id": str(user_id) if user_id else None,
        "q": f"%{q.strip()}%" if q and q.strip() else None,
        "limit": limit,
    }
    rows = (
        await db.execute(
            text(
                """
                WITH wallet_tx AS (
                  SELECT
                    wt.transaction_id AS movement_id,
                    wt.user_id,
                    wt.wallet_id,
                    wt.amount,
                    wt.currency_code,
                    wt.direction,
                    wt.operation_type,
                    wt.reference,
                    wt.description,
                    wt.balance_after,
                    wt.created_at,
                    CASE
                      WHEN wt.reference ~* '^[0-9a-f-]{36}$' THEN CAST(wt.reference AS uuid)
                      ELSE NULL
                    END AS direct_admin_user_id
                  FROM paylink.wallet_transactions wt
                  WHERE wt.operation_type IN ('cash_deposit_admin_direct', 'cash_deposit_admin')
                    AND wt.direction IN ('credit', 'CREDIT')
                ),
                cash_request_meta AS (
                  SELECT
                    wcr.request_id AS cash_request_id,
                    wcr.user_id,
                    wcr.amount,
                    wcr.currency_code,
                    wcr.processed_at,
                    wcr.processed_by AS processed_by_admin_id,
                    wcr.admin_note
                  FROM paylink.wallet_cash_requests wcr
                  WHERE CAST(wcr.type AS text) IN ('DEPOSIT', 'deposit')
                    AND CAST(wcr.status AS text) IN ('APPROVED', 'approved')
                ),
                joined AS (
                  SELECT
                    tx.movement_id,
                    tx.user_id,
                    tx.wallet_id,
                    tx.amount,
                    tx.currency_code,
                    tx.operation_type,
                    tx.reference,
                    tx.description,
                    tx.balance_after,
                    tx.created_at AS deposit_created_at,
                    crm.cash_request_id,
                    COALESCE(crm.processed_by_admin_id, tx.direct_admin_user_id) AS processed_by_admin_id,
                    crm.admin_note
                  FROM wallet_tx tx
                  LEFT JOIN cash_request_meta crm
                    ON crm.user_id = tx.user_id
                   AND crm.amount = tx.amount
                   AND crm.currency_code = tx.currency_code
                   AND crm.processed_at IS NOT NULL
                   AND ABS(EXTRACT(EPOCH FROM (crm.processed_at - tx.created_at))) <= 10
                )
                SELECT
                  j.deposit_created_at,
                  u.user_id,
                  u.full_name AS user_full_name,
                  u.email AS user_email,
                  j.wallet_id,
                  j.amount,
                  j.currency_code,
                  j.operation_type,
                  CASE
                    WHEN j.operation_type = 'cash_deposit_admin_direct' THEN 'depot_admin_direct'
                    WHEN j.operation_type = 'cash_deposit_admin' THEN 'depot_admin_via_validation'
                    ELSE j.operation_type
                  END AS deposit_mode,
                  j.balance_after AS new_balance,
                  j.cash_request_id,
                  j.movement_id,
                  j.reference,
                  j.description,
                  j.admin_note,
                  admin_user.user_id AS admin_user_id,
                  admin_user.full_name AS admin_full_name,
                  admin_user.email AS admin_email
                FROM joined j
                JOIN paylink.users u ON u.user_id = j.user_id
                LEFT JOIN paylink.users admin_user ON admin_user.user_id = j.processed_by_admin_id
                WHERE (:user_id IS NULL OR j.user_id = CAST(:user_id AS uuid))
                  AND (
                    :q IS NULL
                    OR u.full_name ILIKE :q
                    OR u.email ILIKE :q
                    OR u.phone_e164 ILIKE :q
                    OR admin_user.full_name ILIKE :q
                    OR admin_user.email ILIKE :q
                    OR j.reference ILIKE :q
                  )
                ORDER BY j.deposit_created_at DESC
                LIMIT :limit
                """
            ).bindparams(
                bindparam("user_id", type_=String()),
                bindparam("q", type_=String()),
                bindparam("limit", type_=Integer()),
            ),
            params,
        )
    ).mappings().all()
    return [AdminCashDepositSearchRead.model_validate(dict(row)) for row in rows]


@router.post("/deposit")
async def admin_cash_deposit_direct(
    payload: AdminCashDepositCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    note = (payload.note or "").strip() or _default_admin_cash_note("direct_deposit", WalletCashRequestType.DEPOSIT)

    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "user_id": str(payload.user_id),
                "amount": str(payload.amount),
                "note": note,
                "actor": str(admin.user_id),
                "operation": "admin_cash_deposit_direct",
            }
        )
        scoped_idempotency_key = f"admin_cash_deposit_direct:{admin.user_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key deja utilisee avec un payload different.",
            )
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

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
    recovery = await apply_cash_deposit_with_credit_recovery(
        db,
        user=user,
        wallet=wallet,
        amount=amount,
        credit_event_source="cash_deposit_admin_direct",
        credit_history_description="Depot cash direct admin",
    )
    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=user.user_id,
        amount=amount,
        direction="credit",
        operation_type="cash_deposit_admin_direct",
        reference=str(admin.user_id),
        description=f"Depot cash direct admin ({note})",
    )
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_in = await ledger.get_cash_in_account(wallet.currency_code)
    await ledger.post_journal(
        tx_id=None,
        description="Depot cash direct admin",
        metadata={
            "operation": "cash_deposit_admin_direct",
            "target_user_id": str(user.user_id),
            "wallet_id": str(wallet.wallet_id),
            "processed_by": str(admin.user_id),
            "note": note,
            "credit_recovered": str(recovery["credit_recovered"]),
            "credit_available_after": (
                str(recovery["credit_available_after"])
                if recovery["credit_available_after"] is not None
                else None
            ),
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
    response_payload = {
        "message": "Depot cash effectue",
        "user_id": str(user.user_id),
        "wallet_id": str(wallet.wallet_id),
        "amount": float(amount),
        "currency": wallet.currency_code,
        "new_balance": float(wallet.available),
        "credit_recovered": float(recovery["credit_recovered"]),
    }
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload,
        )
    await db.commit()
    return response_payload


@router.post("/withdraw")
async def admin_cash_withdraw_direct(
    payload: AdminCashDepositCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    note = (payload.note or "").strip() or _default_admin_cash_note("direct_deposit", WalletCashRequestType.WITHDRAW)

    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "user_id": str(payload.user_id),
                "amount": str(payload.amount),
                "note": note,
                "actor": str(admin.user_id),
                "operation": "admin_cash_withdraw_direct",
            }
        )
        scoped_idempotency_key = f"admin_cash_withdraw_direct:{admin.user_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key deja utilisee avec un payload different.",
            )
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

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
        raise HTTPException(status_code=404, detail="Wallet introuvable")

    ledger = LedgerService(db)
    amount = decimal.Decimal(payload.amount)
    try:
        usage = await apply_cash_withdraw_with_credit_usage(
            db,
            user=user,
            wallet=wallet,
            amount=amount,
            credit_event_source="cash_withdraw_admin_direct",
            credit_history_description="Retrait cash direct admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=user.user_id,
        amount=amount,
        direction="debit",
        operation_type="cash_withdraw_admin_direct",
        reference=str(admin.user_id),
        description=f"Retrait cash direct admin ({note})",
    )
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_out = await ledger.get_cash_out_account(wallet.currency_code)
    await ledger.post_journal(
        tx_id=None,
        description="Retrait cash direct admin",
        metadata={
            "operation": "cash_withdraw_admin_direct",
            "target_user_id": str(user.user_id),
            "wallet_id": str(wallet.wallet_id),
            "processed_by": str(admin.user_id),
            "note": note,
            "credit_consumed": str(usage["credit_consumed"]),
            "credit_available_after": (
                str(usage["credit_available_after"])
                if usage["credit_available_after"] is not None
                else None
            ),
            "movement_id": str(movement.transaction_id) if movement else None,
        },
        entries=[
            LedgerLine(
                account=wallet_account,
                direction="debit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
            LedgerLine(
                account=cash_out,
                direction="credit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
        ],
    )
    response_payload = {
        "message": "Retrait cash effectue",
        "user_id": str(user.user_id),
        "wallet_id": str(wallet.wallet_id),
        "amount": float(amount),
        "currency": wallet.currency_code,
        "new_balance": float(wallet.available),
        "credit_consumed": float(usage["credit_consumed"]),
    }
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload,
        )
    await db.commit()
    return response_payload


@router.post("/{request_id}/approve", response_model=WalletCashRequestAdminRead)
async def approve_cash_request(
    request_id: UUID,
    payload: WalletCashDecision,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    note = (payload.note or "").strip() or _default_admin_cash_note("approve", None)
    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "action": "approve_cash_request",
                "request_id": str(request_id),
                "note": note,
                "actor": str(admin.user_id),
            }
        )
        scoped_idempotency_key = f"cash_request_approve:{admin.user_id}:{request_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key deja utilisee avec un payload different.",
            )
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

    request = await db.get(WalletCashRequests, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    note = (payload.note or "").strip() or _default_admin_cash_note("approve", request.type)
    transition_cash_request_status(request, WalletCashRequestStatus.APPROVED)

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
        user = await db.get(Users, wallet.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        recovery = await apply_cash_deposit_with_credit_recovery(
            db,
            user=user,
            wallet=wallet,
            amount=decimal.Decimal(request.amount or 0),
            credit_event_source="cash_deposit_admin",
            credit_history_description="Validation depot cash admin",
        )
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
        cash_in = await ledger.get_cash_in_account(wallet.currency_code)
        await ledger.post_journal(
            tx_id=None,
            description="Validation dépôt cash",
            metadata=(
                metadata
                | ({"movement_id": str(movement.transaction_id)} if movement else {})
                | {"credit_recovered": str(recovery["credit_recovered"])}
                | (
                    {"credit_available_after": str(recovery["credit_available_after"])}
                    if recovery["credit_available_after"] is not None
                    else {}
                )
            ),
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
        user = await db.get(Users, wallet.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        try:
            usage = await apply_cash_withdraw_with_credit_usage(
                db,
                user=user,
                wallet=wallet,
                amount=total,
                credit_event_source="cash_withdraw_admin",
                credit_history_description="Validation retrait cash admin",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        cash_out = await ledger.get_cash_out_account(wallet.currency_code)
        await ledger.post_journal(
            tx_id=None,
            description="Validation retrait cash",
            metadata=metadata
            | ({"movement_id": str(movement.transaction_id)} if movement else {})
            | {"credit_consumed": str(usage["credit_consumed"])}
            | (
                {"credit_available_after": str(usage["credit_available_after"])}
                if usage["credit_available_after"] is not None
                else {}
            ),
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

    request.admin_note = note
    request.processed_by = admin.user_id
    request.processed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(request)
    response_payload = (await _serialize_request(db, request)).model_dump(mode="json")
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload,
        )
        await db.commit()
    return response_payload


@router.post("/{request_id}/reject", response_model=WalletCashRequestAdminRead)
async def reject_cash_request(
    request_id: UUID,
    payload: WalletCashDecision,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    note = (payload.note or "").strip() or _default_admin_cash_note("reject", None)

    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "action": "reject_cash_request",
                "request_id": str(request_id),
                "note": note,
                "actor": str(admin.user_id),
            }
        )
        scoped_idempotency_key = f"cash_request_reject:{admin.user_id}:{request_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key deja utilisee avec un payload different.",
            )
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

    request = await db.get(WalletCashRequests, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    note = (payload.note or "").strip() or _default_admin_cash_note("reject", request.type)
    transition_cash_request_status(request, WalletCashRequestStatus.REJECTED)
    request.admin_note = note
    request.processed_by = admin.user_id
    request.processed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(request)
    response_payload = (await _serialize_request(db, request)).model_dump(mode="json")
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload,
        )
        await db.commit()
    return response_payload

from decimal import Decimal
from datetime import datetime
from uuid import uuid4
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Literal

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.models.wallets import Wallets
from app.models.wallet_transactions import WalletTransactions
from app.services.wallet_history import log_wallet_movement
from app.services.wallet_service import (
    _crypto_wallet_account_code,
    ensure_usdc_wallet_account,
    ensure_usdt_wallet_account,
    get_crypto_balance,
)

router = APIRouter(prefix="/admin/wallets", tags=["Admin Wallets"])


def _normalize_wallet_direction(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"credit", "in"}:
        return "credit"
    if normalized in {"debit", "out"}:
        return "debit"
    return normalized or "unknown"


async def _crypto_wallet_account_exists(db: AsyncSession, user_id: str, token_symbol: str) -> bool:
    account_code = _crypto_wallet_account_code(user_id, token_symbol)
    res = await db.execute(
        text(
            """
            SELECT 1
            FROM paylink.ledger_accounts
            WHERE code = :code
            LIMIT 1
            """
        ),
        {"code": account_code},
    )
    return res.first() is not None


def compute_alert_label(balance: Decimal) -> str:
    if balance is None:
        return "unknown"
    if balance < Decimal("0"):
        return "critical"
    if balance < Decimal("10000"):
        return "warning"
    return "ok"


WalletCorrectionScenario = Literal[
    "credit_adjustment",
    "debit_adjustment",
    "set_available_balance",
    "clear_negative_balance",
]


class WalletCorrectionPreviewRequest(BaseModel):
    wallet_id: UUID
    scenario: WalletCorrectionScenario
    amount: Decimal | None = Field(default=None, gt=0)
    target_balance: Decimal | None = None
    reason: str = Field(..., min_length=3, max_length=300)
    note: str | None = Field(default=None, max_length=500)


def _wallet_correction_operation_type(scenario: WalletCorrectionScenario) -> str:
    return {
        "credit_adjustment": "admin_wallet_correction_credit",
        "debit_adjustment": "admin_wallet_correction_debit",
        "set_available_balance": "admin_wallet_correction_set_balance",
        "clear_negative_balance": "admin_wallet_correction_clear_negative",
    }[scenario]


def _serialize_decimal(value: Decimal | None) -> float:
    return float(value or 0)


async def _load_wallet_with_user(db: AsyncSession, wallet_id: UUID):
    row = await db.execute(
        select(Wallets, Users)
        .join(Users, Users.user_id == Wallets.user_id, isouter=True)
        .where(Wallets.wallet_id == wallet_id)
    )
    result = row.first()
    if not result:
        raise HTTPException(404, "Wallet introuvable")
    return result


def _build_wallet_correction_preview(wallet: Wallets, payload: WalletCorrectionPreviewRequest) -> dict:
    wallet_before = Decimal(wallet.available or 0)
    pending = Decimal(wallet.pending or 0)
    scenario = payload.scenario
    if scenario == "credit_adjustment":
        if payload.amount is None:
            raise HTTPException(400, "Le montant est requis pour ce scenario.")
        signed_delta = Decimal(payload.amount)
    elif scenario == "debit_adjustment":
        if payload.amount is None:
            raise HTTPException(400, "Le montant est requis pour ce scenario.")
        signed_delta = -Decimal(payload.amount)
    elif scenario == "set_available_balance":
        if payload.target_balance is None:
            raise HTTPException(400, "Le solde cible est requis pour ce scenario.")
        signed_delta = Decimal(payload.target_balance) - wallet_before
    elif scenario == "clear_negative_balance":
        if wallet_before >= 0:
            raise HTTPException(400, "Le wallet n'est pas negatif. Ce scenario ne s'applique pas.")
        signed_delta = abs(wallet_before)
    else:
        raise HTTPException(400, "Scenario non supporte.")

    if signed_delta == 0:
        raise HTTPException(400, "Aucune correction a appliquer: le delta calcule est nul.")

    wallet_after = wallet_before + signed_delta
    direction = "credit" if signed_delta > 0 else "debit"
    operation_type = _wallet_correction_operation_type(scenario)
    warnings: list[str] = []
    if wallet_after < 0:
        warnings.append("Le wallet restera negatif apres correction.")
    if pending != 0:
        warnings.append("La correction n'affecte pas le solde pending.")

    implications = [
        "Met a jour wallets.available.",
        "Cree une ligne wallet_transactions avec reference admin.",
        "Cree un client_balance_event pour tracer l'impact client.",
        "Ne modifie ni pending, ni bonus_balance, ni ligne de credit.",
        "La correction est historisee: en cas d'erreur, il faut une contre-correction.",
    ]
    return {
        "wallet_id": str(wallet.wallet_id),
        "user_id": str(wallet.user_id) if wallet.user_id else None,
        "currency_code": wallet.currency_code,
        "scenario": scenario,
        "direction": direction,
        "amount": _serialize_decimal(abs(signed_delta)),
        "signed_delta": _serialize_decimal(signed_delta),
        "wallet_before": _serialize_decimal(wallet_before),
        "wallet_after": _serialize_decimal(wallet_after),
        "pending_before": _serialize_decimal(pending),
        "operation_type": operation_type,
        "reason": payload.reason,
        "note": payload.note,
        "implications": implications,
        "warnings": warnings,
        "can_apply": True,
    }


@router.get("")
@router.get("/")
async def list_wallet_alerts(
    min_available: float | None = Query(
        None, description="Filtre solde max (None = 50 plus bas)"
    ),
    wallet_type: str | None = Query(None, description="Filtre par type de wallet"),
    user_id: UUID | None = Query(None, description="Filtre par utilisateur"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(
            Wallets.wallet_id,
            cast(Wallets.type, String).label("wallet_type"),
            Wallets.currency_code,
            Wallets.available,
            Wallets.pending,
            Users.user_id,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == Wallets.user_id, isouter=True)
        .order_by(Wallets.available.asc())
        .limit(limit)
    )

    if min_available is not None:
        stmt = stmt.where(func.coalesce(Wallets.available, 0) <= min_available)
    if wallet_type:
        stmt = stmt.where(cast(Wallets.type, String) == wallet_type)
    if user_id is not None:
        stmt = stmt.where(Wallets.user_id == user_id)

    rows = (await db.execute(stmt)).all()

    return [
        {
            "wallet_id": str(r.wallet_id),
            "type": r.wallet_type,
            "currency": r.currency_code,
            "available": float(r.available or 0),
            "pending": float(r.pending or 0),
            "user_id": str(r.user_id) if r.user_id else None,
            "user_name": r.full_name,
            "user_email": r.email,
            "alert": compute_alert_label(r.available),
        }
        for r in rows
    ]


@router.get("/summary")
async def wallets_summary(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    total_wallets = await db.scalar(select(func.count(Wallets.wallet_id)))
    negative_wallets = await db.scalar(
        select(func.count(Wallets.wallet_id)).where(Wallets.available < 0)
    )
    low_balance_wallets = await db.scalar(
        select(func.count(Wallets.wallet_id)).where(Wallets.available < 10)
    )

    return {
        "total_wallets": total_wallets or 0,
        "negative_wallets": negative_wallets or 0,
        "low_balance_wallets": low_balance_wallets or 0,
    }


@router.post("/corrections/preview")
async def preview_wallet_correction(
    payload: WalletCorrectionPreviewRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    wallet, user = await _load_wallet_with_user(db, payload.wallet_id)
    preview = _build_wallet_correction_preview(wallet, payload)
    preview.update(
        {
            "user_name": getattr(user, "full_name", None),
            "user_email": getattr(user, "email", None),
            "wallet_type": str(getattr(wallet, "type", "") or ""),
        }
    )
    return preview


@router.post("/corrections/apply")
async def apply_wallet_correction(
    payload: WalletCorrectionPreviewRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    wallet, user = await _load_wallet_with_user(db, payload.wallet_id)
    preview = _build_wallet_correction_preview(wallet, payload)
    signed_delta = Decimal(str(preview["signed_delta"]))
    amount = abs(signed_delta)
    wallet.available = Decimal(wallet.available or 0) + signed_delta
    reference = f"ADMIN-WALLET-CORR-{uuid4().hex[:12].upper()}"
    description = payload.reason.strip()
    if payload.note:
        description = f"{description} | {payload.note.strip()}"

    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=wallet.user_id,
        amount=amount,
        direction=preview["direction"],
        operation_type=preview["operation_type"],
        reference=reference,
        description=description,
    )
    await db.commit()

    return {
        "message": "Correction wallet appliquee.",
        "reference": reference,
        "movement_id": str(movement.transaction_id) if movement else None,
        "preview": {
            **preview,
            "wallet_after": _serialize_decimal(Decimal(wallet.available or 0)),
        },
        "wallet": {
            "wallet_id": str(wallet.wallet_id),
            "user_id": str(wallet.user_id) if wallet.user_id else None,
            "user_name": getattr(user, "full_name", None),
            "user_email": getattr(user, "email", None),
            "currency_code": wallet.currency_code,
            "wallet_type": str(getattr(wallet, "type", "") or ""),
            "available": _serialize_decimal(Decimal(wallet.available or 0)),
            "pending": _serialize_decimal(Decimal(wallet.pending or 0)),
        },
    }


@router.get("/{wallet_id}/history")
async def wallet_history_admin(
    wallet_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    wallet = await db.scalar(select(Wallets.wallet_id).where(Wallets.wallet_id == wallet_id))
    if not wallet:
        raise HTTPException(404, "Wallet introuvable")

    stmt = (
        select(
            WalletTransactions.transaction_id,
            WalletTransactions.amount,
            cast(WalletTransactions.direction, String).label("direction"),
            WalletTransactions.balance_after,
            WalletTransactions.operation_type,
            WalletTransactions.reference,
            WalletTransactions.description,
            WalletTransactions.created_at,
            Users.full_name,
            Users.email,
        )
        .join(Users, Users.user_id == WalletTransactions.user_id, isouter=True)
        .where(WalletTransactions.wallet_id == wallet_id)
        .order_by(WalletTransactions.created_at.desc())
        .limit(limit)
    )

    if from_date:
        stmt = stmt.where(WalletTransactions.created_at >= from_date)
    if to_date:
        stmt = stmt.where(WalletTransactions.created_at <= to_date)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            WalletTransactions.reference.ilike(pattern)
            | WalletTransactions.operation_type.ilike(pattern)
            | WalletTransactions.description.ilike(pattern)
            | cast(WalletTransactions.amount, String).ilike(pattern)
        )

    rows = (await db.execute(stmt)).all()
    return [
        {
            "transaction_id": str(r.transaction_id),
            "amount": float(r.amount),
            "direction": _normalize_wallet_direction(r.direction),
            "balance_after": float(r.balance_after),
            "operation_type": r.operation_type,
            "reference": r.reference,
            "description": r.description or "",
            "created_at": r.created_at.isoformat(),
            "user_name": r.full_name,
            "user_email": r.email,
        }
        for r in rows
    ]


@router.get("/crypto/{user_id}/summary")
async def admin_crypto_wallet_summary(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    normalized_user_id = str(user_id)
    wallets = []
    for token_symbol in ("USDC", "USDT"):
        exists = await _crypto_wallet_account_exists(db, normalized_user_id, token_symbol)
        balance = await get_crypto_balance(normalized_user_id, token_symbol, db=db) if exists else Decimal("0")
        wallets.append(
            {
                "token_symbol": token_symbol,
                "exists": exists,
                "balance": float(balance),
                "account_code": _crypto_wallet_account_code(normalized_user_id, token_symbol),
            }
        )
    return {"user_id": normalized_user_id, "wallets": wallets}


@router.post("/crypto/{user_id}/ensure")
async def admin_ensure_crypto_wallet(
    user_id: UUID,
    token_symbol: str = Query(..., min_length=4, max_length=4),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    normalized_user_id = str(user_id)
    normalized_token = str(token_symbol or "").strip().upper()
    if normalized_token == "USDC":
        account_code = await ensure_usdc_wallet_account(normalized_user_id, db=db)
    elif normalized_token == "USDT":
        account_code = await ensure_usdt_wallet_account(normalized_user_id, db=db)
    else:
        raise HTTPException(status_code=400, detail="Token non supporte")
    await db.commit()
    balance = await get_crypto_balance(normalized_user_id, normalized_token, db=db)
    return {
        "user_id": normalized_user_id,
        "token_symbol": normalized_token,
        "account_code": account_code,
        "balance": float(balance),
        "created": True,
    }


@router.get("/crypto/{user_id}/history")
async def admin_crypto_wallet_history(
    user_id: UUID,
    token_symbol: str = Query(..., min_length=4, max_length=4),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    normalized_user_id = str(user_id)
    normalized_token = str(token_symbol or "").strip().upper()
    if normalized_token == "USDC":
        await ensure_usdc_wallet_account(normalized_user_id, db=db)
    elif normalized_token == "USDT":
        await ensure_usdt_wallet_account(normalized_user_id, db=db)
    else:
        raise HTTPException(status_code=400, detail="Token non supporte")

    account_code = _crypto_wallet_account_code(normalized_user_id, normalized_token)
    query = """
        SELECT
          j.journal_id,
          j.description,
          j.metadata,
          j.occurred_at,
          e.direction,
          e.amount,
          e.currency_code
        FROM paylink.ledger_journal j
        JOIN paylink.ledger_entries e ON e.journal_id = j.journal_id
        JOIN paylink.ledger_accounts a ON a.account_id = e.account_id
        WHERE a.code = :account_code
          AND e.currency_code = :currency
    """
    params = {
        "account_code": account_code,
        "currency": normalized_token,
        "limit": int(limit),
    }
    if from_date is not None:
        query += " AND j.occurred_at >= :from_date"
        params["from_date"] = from_date
    if to_date is not None:
        query += " AND j.occurred_at <= :to_date"
        params["to_date"] = to_date
    if search:
        query += """
          AND (
            COALESCE(j.description, '') ILIKE :pattern
            OR COALESCE(j.metadata->>'ref', '') ILIKE :pattern
            OR COALESCE(j.metadata->>'event', '') ILIKE :pattern
          )
        """
        params["pattern"] = f"%{search.strip()}%"

    query += " ORDER BY j.occurred_at DESC LIMIT :limit"
    rows = (await db.execute(text(query), params)).mappings().all()
    running_balance = await get_crypto_balance(normalized_user_id, normalized_token, db=db)

    entries = []
    for row in rows:
        direction_flag = str(row["direction"] or "").lower()
        signed_amount = float(row["amount"]) * (1 if direction_flag.startswith("debit") else -1)
        metadata = row["metadata"] or {}
        if isinstance(metadata, str):
            metadata = {}
        entries.append(
            {
                "transaction_id": str(row["journal_id"]),
                "amount": signed_amount,
                "direction": "credit" if signed_amount >= 0 else "debit",
                "balance_after": float(running_balance),
                "created_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
                "reference": metadata.get("ref") or "-",
                "operation_type": metadata.get("event") or row["description"] or "CRYPTO_WALLET",
                "description": row["description"] or "",
                "currency_code": row["currency_code"],
            }
        )
        running_balance = Decimal(str(running_balance)) - Decimal(str(signed_amount))

    return entries


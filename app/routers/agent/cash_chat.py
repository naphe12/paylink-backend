import decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cash_chat.schemas import CashChatRequest, CashChatResponse, ConfirmCashChatRequest
from app.cash_chat.service import cancel_cash_request, process_cash_message, SUPPORTED_CASH_PROVIDERS
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.models.wallets import Wallets
from app.models.wallet_cash_requests import (
    WalletCashRequestStatus,
    WalletCashRequestType,
    WalletCashRequests,
)
from app.schemas.wallet_cash_requests import WalletCashRequestRead
from app.services.idempotency_service import (
    acquire_idempotency,
    compute_request_hash,
    store_idempotency_response,
)
from app.routers.agent._target_user import resolve_target_user_context


router = APIRouter(prefix="/agent/cash-chat", tags=["Cash Agent"])


def _build_cash_request_reference(request_id, request_type) -> str:
    type_token = str(getattr(request_type, "value", request_type) or "").strip().upper()
    prefix = {
        "DEPOSIT": "DEP",
        "WITHDRAW": "WDR",
        "EXTERNAL_TRANSFER": "EXT",
    }.get(type_token, "CSH")
    raw = str(request_id or "").replace("-", "").upper()
    return f"{prefix}-{raw[:10]}"


@router.post("", response_model=CashChatResponse)
async def cash_chat_agent(
    payload: CashChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    target_context = await resolve_target_user_context(
        db,
        current_user,
        payload.target_user_id,
        payload.message,
    )
    return await process_cash_message(
        db,
        user_id=target_context.user_id,
        message=target_context.message,
    )


@router.post("/cancel", response_model=CashChatResponse)
async def cancel_cash_chat(
    current_user: Users = Depends(get_current_user),
):
    return cancel_cash_request()


@router.post("/confirm")
async def confirm_cash_chat(
    payload: ConfirmCashChatRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    draft = payload.draft
    if draft.intent not in {"deposit", "withdraw"}:
        return CashChatResponse(
            status="NEED_INFO",
            message="Seules les demandes de depot et de retrait peuvent etre confirmees.",
            data=draft,
            executable=False,
        )

    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    amount = decimal.Decimal(draft.amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide")

    if draft.intent == "withdraw":
        if not draft.mobile_number:
            raise HTTPException(status_code=400, detail="Numero mobile requis")
        if not draft.provider_name or str(draft.provider_name) not in SUPPORTED_CASH_PROVIDERS:
            raise HTTPException(status_code=400, detail="Operateur non supporte")
        fee = (amount * decimal.Decimal("0.0625")).quantize(decimal.Decimal("0.000001"))
        total = amount + fee
        wallet_balance = decimal.Decimal(wallet.available or 0)
        if wallet_balance < total:
            raise HTTPException(status_code=400, detail="Solde insuffisant pour ce retrait")
        request_type = WalletCashRequestType.WITHDRAW
        payload_hash = compute_request_hash(
            {
                "amount": str(amount),
                "mobile_number": draft.mobile_number,
                "provider_name": draft.provider_name,
                "note": draft.note,
                "type": "withdraw",
                "user_id": str(current_user.user_id),
            }
        )
        scoped_prefix = "wallet_cash_withdraw"
    else:
        fee = decimal.Decimal("0")
        total = amount
        request_type = WalletCashRequestType.DEPOSIT
        payload_hash = compute_request_hash(
            {
                "amount": str(amount),
                "note": draft.note,
                "type": "deposit",
                "user_id": str(current_user.user_id),
            }
        )
        scoped_prefix = "wallet_cash_deposit"

    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        scoped_idempotency_key = f"{scoped_prefix}:{current_user.user_id}:{idempotency_key.strip()}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(status_code=409, detail="Idempotency-Key deja utilisee avec un payload different.")
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

    request = WalletCashRequests(
        user_id=current_user.user_id,
        wallet_id=wallet.wallet_id,
        type=request_type,
        status=WalletCashRequestStatus.PENDING,
        amount=amount,
        fee_amount=fee,
        total_amount=total,
        currency_code=wallet.currency_code,
        mobile_number=draft.mobile_number if draft.intent == "withdraw" else None,
        provider_name=draft.provider_name if draft.intent == "withdraw" else None,
        note=draft.note,
        metadata_={
            "source": "cash_agent_chat",
            "raw_message": str(draft.raw_message or "").strip(),
        },
    )
    db.add(request)
    await db.flush()
    await db.refresh(request)
    response_payload = WalletCashRequestRead.model_validate(request).model_copy(
        update={"reference_code": _build_cash_request_reference(request.request_id, request.type)}
    )
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload.model_dump(mode="json"),
        )
    await db.commit()
    return {
        "status": "DONE",
        "message": "Demande cash creee avec succes.",
        "request": response_payload.model_dump(mode="json"),
    }

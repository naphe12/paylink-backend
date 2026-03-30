from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.confirmation_service import load_pending_action
from app.ai.orchestrator import handle_message
from app.ai.policy_guard import check_policy
from app.ai.schemas import AiConfirmRequest, AiMessageRequest, AiResponse, ResolvedCommand
from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user_db
from app.models.ai_audit_logs import AiAuditLogs
from app.models.external_beneficiaries import ExternalBeneficiaries
from app.models.users import Users
from app.models.wallet_cash_requests import WalletCashRequestStatus, WalletCashRequestType, WalletCashRequests
from app.models.wallets import Wallets
from app.schemas.external_transfers import ExternalTransferCreate
from app.schemas.wallet_cash_requests import WalletCashRequestRead

router = APIRouter(prefix="/ai", tags=["AI"])
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_TARGETED_TEST_PATH = "app/tests/test_ai_gateway_targeted.py"


def _normalize_beneficiary_account(value) -> str:
    return str(value or "").strip().lower()


def _build_cash_request_reference(request_id, request_type) -> str:
    type_token = str(getattr(request_type, "value", request_type) or "").strip().upper()
    prefix = {
        "DEPOSIT": "DEP",
        "WITHDRAW": "WDR",
        "EXTERNAL_TRANSFER": "EXT",
    }.get(type_token, "CSH")
    raw = str(request_id or "").replace("-", "").upper()
    return f"{prefix}-{raw[:10]}"


async def _write_audit_log(
    db: AsyncSession,
    *,
    current_user: Users,
    session_id,
    raw_message: str,
    parsed_intent: dict | None,
    resolved_command: dict | None,
    action_taken: str,
    status: str,
    error_message: str | None = None,
) -> None:
    db.add(
        AiAuditLogs(
            user_id=current_user.user_id,
            session_id=session_id,
            raw_message=raw_message,
            parsed_intent=parsed_intent,
            resolved_command=resolved_command,
            action_taken=action_taken,
            status=status,
            error_message=error_message,
        )
    )
    await db.flush()


@router.post("/message", response_model=AiResponse)
async def ai_message(
    payload: AiMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=payload.message,
        session_id=payload.session_id,
    )
    await _write_audit_log(
        db,
        current_user=current_user,
        session_id=payload.session_id,
        raw_message=payload.message,
        parsed_intent=parsed.model_dump(mode="json") if parsed else None,
        resolved_command=resolved,
        action_taken=response.type,
        status="ok",
    )
    await db.commit()
    return response


@router.post("/confirm", response_model=AiResponse)
async def ai_confirm(
    payload: AiConfirmRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    pending = await load_pending_action(db, pending_action_id=payload.pending_action_id, current_user=current_user)
    if pending is None:
        raise HTTPException(status_code=404, detail="Action en attente introuvable")
    if str(pending.status) != "pending":
        raise HTTPException(status_code=409, detail="Cette action n'est plus en attente")
    if pending.expires_at and pending.expires_at < datetime.now(timezone.utc):
        pending.status = "expired"
        await db.commit()
        raise HTTPException(status_code=409, detail="Cette action a expire")

    if not payload.confirm:
        pending.status = "cancelled"
        pending.confirmed_at = datetime.now(timezone.utc)
        await _write_audit_log(
            db,
            current_user=current_user,
            session_id=pending.session_id,
            raw_message="confirm:false",
            parsed_intent={"intent": pending.intent_code},
            resolved_command={"action_code": pending.action_code, "payload": pending.payload},
            action_taken="cancelled",
            status="ok",
        )
        await db.commit()
        return AiResponse(type="cancelled", message="Action annulee.", pending_action_id=pending.id)

    if pending.intent_code == "beneficiary.add":
        command_payload = dict(pending.payload or {})
        normalized_account = _normalize_beneficiary_account(
            command_payload.get("account_ref") or command_payload.get("recipient_email")
        )
        existing = await db.scalar(
            select(ExternalBeneficiaries).where(
                ExternalBeneficiaries.user_id == current_user.user_id,
                ExternalBeneficiaries.partner_name == str(command_payload.get("partner_name") or ""),
                ExternalBeneficiaries.recipient_phone == str(command_payload.get("recipient_phone") or ""),
                func.coalesce(func.lower(ExternalBeneficiaries.recipient_email), "") == normalized_account,
            )
        )
        if existing is None:
            existing = ExternalBeneficiaries(
                user_id=current_user.user_id,
                recipient_name=str(command_payload.get("recipient_name") or ""),
                recipient_phone=str(command_payload.get("recipient_phone") or ""),
                recipient_email=normalized_account or None,
                partner_name=str(command_payload.get("partner_name") or ""),
                country_destination=str(command_payload.get("country_destination") or ""),
                is_active=True,
            )
            db.add(existing)
            action_message = f"Beneficiaire {existing.recipient_name} enregistre."
        else:
            existing.recipient_name = str(command_payload.get("recipient_name") or existing.recipient_name)
            existing.recipient_email = normalized_account or existing.recipient_email
            existing.country_destination = str(command_payload.get("country_destination") or existing.country_destination)
            existing.is_active = True
            action_message = f"Beneficiaire {existing.recipient_name} mis a jour."
        pending.status = "executed"
        pending.confirmed_at = datetime.now(timezone.utc)
        pending.executed_at = datetime.now(timezone.utc)
        pending.result_payload = {
            "recipient_name": existing.recipient_name,
            "recipient_phone": existing.recipient_phone,
            "account_ref": existing.recipient_email,
            "partner_name": existing.partner_name,
            "country_destination": existing.country_destination,
        }
        await _write_audit_log(
            db,
            current_user=current_user,
            session_id=pending.session_id,
            raw_message="confirm:true",
            parsed_intent={"intent": pending.intent_code},
            resolved_command={"action_code": pending.action_code, "payload": pending.payload},
            action_taken="executed",
            status="ok",
        )
        await db.commit()
        return AiResponse(
            type="executed",
            message=action_message,
            pending_action_id=pending.id,
            data=pending.result_payload,
        )

    if pending.intent_code in {"cash.deposit", "cash.withdraw"}:
        command_payload = dict(pending.payload or {})
        wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
        if wallet is None:
            raise HTTPException(status_code=404, detail="Portefeuille introuvable")
        amount = Decimal(str(command_payload.get("amount") or "0"))
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Montant invalide")
        if pending.intent_code == "cash.withdraw":
            mobile_number = str(command_payload.get("mobile_number") or "").strip()
            provider_name = str(command_payload.get("provider_name") or "").strip()
            if not mobile_number or not provider_name:
                raise HTTPException(status_code=400, detail="Informations de retrait incompletes")
            fee = (amount * Decimal("0.0625")).quantize(Decimal("0.000001"))
            total = amount + fee
            if Decimal(wallet.available or 0) < total:
                raise HTTPException(status_code=400, detail="Solde insuffisant pour ce retrait")
            request_type = WalletCashRequestType.WITHDRAW
        else:
            mobile_number = None
            provider_name = None
            fee = Decimal("0")
            total = amount
            request_type = WalletCashRequestType.DEPOSIT
        request = WalletCashRequests(
            user_id=current_user.user_id,
            wallet_id=wallet.wallet_id,
            type=request_type,
            status=WalletCashRequestStatus.PENDING,
            amount=amount,
            fee_amount=fee,
            total_amount=total,
            currency_code=str(command_payload.get("currency") or wallet.currency_code or "EUR"),
            mobile_number=mobile_number,
            provider_name=provider_name,
            note=command_payload.get("note"),
            metadata_={
                "source": "ai_gateway",
            },
        )
        db.add(request)
        await db.flush()
        await db.refresh(request)
        request_payload = WalletCashRequestRead.model_validate(request).model_copy(
            update={"reference_code": _build_cash_request_reference(request.request_id, request.type)}
        )
        pending.status = "executed"
        pending.confirmed_at = datetime.now(timezone.utc)
        pending.executed_at = datetime.now(timezone.utc)
        pending.result_payload = request_payload.model_dump(mode="json")
        await _write_audit_log(
            db,
            current_user=current_user,
            session_id=pending.session_id,
            raw_message="confirm:true",
            parsed_intent={"intent": pending.intent_code},
            resolved_command={"action_code": pending.action_code, "payload": pending.payload},
            action_taken="executed",
            status="ok",
        )
        await db.commit()
        return AiResponse(
            type="executed",
            message="Demande cash creee avec succes.",
            pending_action_id=pending.id,
            data=pending.result_payload,
        )

    if pending.intent_code != "transfer.create":
        pending.status = "confirmed"
        pending.confirmed_at = datetime.now(timezone.utc)
        await db.commit()
        return AiResponse(type="confirmed", message="Action confirmee.", pending_action_id=pending.id)

    command_payload = dict(pending.payload or {})
    policy = await check_policy(
        current_user,
        ResolvedCommand(intent=pending.intent_code, action_code=pending.action_code, payload=command_payload),
    )
    if not policy.allowed:
        pending.status = "cancelled"
        await _write_audit_log(
            db,
            current_user=current_user,
            session_id=pending.session_id,
            raw_message="confirm:true",
            parsed_intent={"intent": pending.intent_code},
            resolved_command={"action_code": pending.action_code, "payload": pending.payload},
            action_taken="refused",
            status="error",
            error_message=policy.reason,
        )
        await db.commit()
        return AiResponse(type="refused", message=policy.reason or "Action refusee.", pending_action_id=pending.id)

    transfer_request = ExternalTransferCreate(
        partner_name=str(command_payload.get("partner_name") or ""),
        country_destination=str(command_payload.get("country_destination") or ""),
        recipient_name=str(command_payload.get("recipient_name") or ""),
        recipient_phone=str(command_payload.get("recipient_phone") or ""),
        recipient_email=command_payload.get("account_ref") or command_payload.get("recipient_email"),
        amount=Decimal(str(command_payload.get("amount") or "0")),
    )
    from app.routers.wallet.transfer import _external_transfer_core

    transfer = await _external_transfer_core(
        data=transfer_request,
        background_tasks=background_tasks,
        idempotency_key=None,
        db=db,
        current_user=current_user,
        override_context={
            "source": "ai_gateway",
            "sender_name": command_payload.get("sender_name"),
            "origin_currency": command_payload.get("origin_currency"),
        },
    )
    transfer_payload = transfer if isinstance(transfer, dict) else transfer.model_dump(mode="json")
    pending.status = "executed"
    pending.confirmed_at = datetime.now(timezone.utc)
    pending.executed_at = datetime.now(timezone.utc)
    pending.result_payload = transfer_payload
    await _write_audit_log(
        db,
        current_user=current_user,
        session_id=pending.session_id,
        raw_message="confirm:true",
        parsed_intent={"intent": pending.intent_code},
        resolved_command={"action_code": pending.action_code, "payload": pending.payload},
        action_taken="executed",
        status="ok",
    )
    await db.commit()
    return AiResponse(
        type="executed",
        message=f"Transfert cree avec la reference {transfer_payload.get('reference_code') or transfer_payload.get('transfer_id')}.",
        pending_action_id=pending.id,
        data=transfer_payload,
    )


@router.post("/cancel", response_model=AiResponse)
async def ai_cancel(
    payload: AiConfirmRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    payload.confirm = False
    return await ai_confirm(payload, background_tasks, db, current_user)


@router.post("/internal/tests/targeted")
async def run_ai_targeted_tests(current_user: Users = Depends(get_current_admin)):
    if settings.APP_ENV == "prod" or not settings.AI_INTERNAL_TESTS_ENABLED:
        raise HTTPException(status_code=404, detail="Endpoint indisponible")

    command = [sys.executable, "-m", "pytest", _TARGETED_TEST_PATH]
    completed = subprocess.run(
        command,
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    combined_output = "\n".join(part for part in [stdout, stderr] if part).strip()
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": " ".join(command),
        "cwd": str(_BACKEND_ROOT),
        "test_file": _TARGETED_TEST_PATH,
        "requested_by": str(current_user.user_id),
        "output": combined_output[:12000],
    }

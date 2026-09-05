from __future__ import annotations

import json
import logging
import traceback
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.scheduled_transfers import ScheduledTransfers
from app.models.credit_lines import CreditLines
from app.models.external_transfers import ExternalTransfers
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.schemas.external_transfers import ExternalTransferCreate
from app.services.ledger import LedgerLine, LedgerService
from app.services.external_transfer_capacity import compute_external_transfer_funding
from app.services.scheduled_transfers_runtime_schema import ensure_scheduled_transfers_schema
from app.services.wallet_history import log_wallet_movement

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _primary_wallet_stmt(user_id):
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
        .with_for_update()
    )


def _advance_next_run(next_run_at: datetime, frequency: str, *, monthly_anchor_day: int | None = None) -> datetime:
    if frequency == "daily":
        return next_run_at + timedelta(days=1)
    if frequency == "weekly":
        return next_run_at + timedelta(days=7)
    if frequency == "monthly":
        try:
            anchor_day = int(monthly_anchor_day or next_run_at.day)
        except (TypeError, ValueError):
            anchor_day = next_run_at.day
        anchor_day = min(max(anchor_day, 1), 31)
        month = next_run_at.month + 1
        year = next_run_at.year
        if month > 12:
            month = 1
            year += 1
        day = min(anchor_day, monthrange(year, month)[1])
        return next_run_at.replace(year=year, month=month, day=day)
    raise ValueError("Unsupported frequency")


def _schedule_is_due(item: ScheduledTransfers) -> bool:
    next_run_at = item.next_run_at
    if next_run_at and next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=timezone.utc)
    return bool(next_run_at and next_run_at <= _utcnow() and item.status in {"active", "failed"})


def _schedule_metadata(item: ScheduledTransfers) -> dict:
    metadata = getattr(item, "metadata_", {}) or {}
    return dict(metadata)


def _schedule_transfer_type(item: ScheduledTransfers) -> str:
    transfer_type = str(_schedule_metadata(item).get("transfer_type") or "internal").strip().lower()
    return "external" if transfer_type == "external" else "internal"


def _schedule_external_payload(item: ScheduledTransfers) -> dict | None:
    payload = _schedule_metadata(item).get("external_transfer")
    return dict(payload) if isinstance(payload, dict) else None


def _schedule_failure_count(item: ScheduledTransfers) -> int:
    metadata = _schedule_metadata(item)
    try:
        return max(int(metadata.get("failure_count") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _schedule_max_consecutive_failures(item: ScheduledTransfers) -> int:
    metadata = _schedule_metadata(item)
    raw = metadata.get("max_consecutive_failures")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 3
    return min(max(value, 1), 10)


def _serialize_schedule(item: ScheduledTransfers) -> dict:
    metadata = _schedule_metadata(item)
    transfer_type = _schedule_transfer_type(item)
    external_transfer = _schedule_external_payload(item)
    failure_count = _schedule_failure_count(item)
    max_consecutive_failures = _schedule_max_consecutive_failures(item)
    receiver_identifier = str(getattr(item, "receiver_identifier", "") or "").strip()
    if transfer_type == "external" and not receiver_identifier:
        receiver_identifier = (
            str((external_transfer or {}).get("recipient_phone") or "").strip()
            or str((external_transfer or {}).get("recipient_name") or "").strip()
            or "-"
        )
    return {
        "schedule_id": item.schedule_id,
        "user_id": item.user_id,
        "receiver_user_id": item.receiver_user_id,
        "receiver_identifier": receiver_identifier,
        "transfer_type": transfer_type,
        "external_transfer": external_transfer,
        "amount": Decimal(str(item.amount)),
        "currency_code": item.currency_code,
        "frequency": item.frequency,
        "status": item.status,
        "note": item.note,
        "next_run_at": item.next_run_at,
        "last_run_at": item.last_run_at,
        "last_result": item.last_result,
        "remaining_runs": item.remaining_runs,
        "failure_count": failure_count,
        "max_consecutive_failures": max_consecutive_failures,
        "auto_paused_for_failures": item.status == "paused" and failure_count >= max_consecutive_failures,
        "metadata": metadata,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "is_due": _schedule_is_due(item),
    }


def _scheduled_transfer_recommended_action(item: ScheduledTransfers, *, transfer_type: str) -> str:
    status = str(getattr(item, "status", "") or "").strip().lower()
    if status == "paused":
        return "reprendre_ou_annuler"
    if status in {"cancelled", "completed"}:
        return "aucune_action"
    if transfer_type == "external":
        return "verifier_statut_externe_et_funding"
    return "executer_ou_surveiller"


def _log_scheduled_transfer_outcome(
    item: ScheduledTransfers,
    *,
    succeeded: bool,
    reason: str,
    exc_info: bool = False,
) -> None:
    log = logger.info if succeeded else (logger.error if exc_info else logger.warning)
    log(
        "Scheduled transfer %s schedule_id=%s user_id=%s transfer_type=%s amount=%s currency=%s "
        "status=%s reason=%s",
        "succeeded" if succeeded else "failed",
        item.schedule_id,
        item.user_id,
        _schedule_transfer_type(item),
        item.amount,
        item.currency_code,
        item.status,
        reason,
        exc_info=exc_info,
    )


async def _persist_scheduled_transfer_execution(
    item: ScheduledTransfers,
    *,
    succeeded: bool,
    reason: str,
    started_at: datetime,
    error: Exception | None = None,
    details: dict | None = None,
) -> None:
    finished_at = _utcnow()
    duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
    stack_trace = None
    if error is not None and not isinstance(error, HTTPException):
        stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))[-12000:]
    try:
        async with async_session_maker() as log_db:
            execution_log_table = await log_db.scalar(
                text("SELECT to_regclass('product_transfers.scheduled_transfer_execution_logs')")
            )
            if execution_log_table is None:
                await ensure_scheduled_transfers_schema(log_db)
            await log_db.execute(
                text(
                    """
                    INSERT INTO product_transfers.scheduled_transfer_execution_logs
                    (schedule_id, user_id, transfer_type, outcome, schedule_status, amount,
                     currency_code, reason, error_type, stack_trace, duration_ms, details, created_at)
                    VALUES
                    (:schedule_id, :user_id, :transfer_type, :outcome, :schedule_status, :amount,
                     :currency_code, :reason, :error_type, :stack_trace, :duration_ms,
                     CAST(:details AS jsonb), :created_at)
                    """
                ),
                {
                    "schedule_id": str(item.schedule_id),
                    "user_id": str(item.user_id),
                    "transfer_type": _schedule_transfer_type(item),
                    "outcome": "succeeded" if succeeded else "failed",
                    "schedule_status": str(item.status),
                    "amount": str(item.amount),
                    "currency_code": str(item.currency_code or ""),
                    "reason": str(reason)[:4000],
                    "error_type": error.__class__.__name__ if error else None,
                    "stack_trace": stack_trace,
                    "duration_ms": duration_ms,
                    "details": json.dumps(details or {}, default=str, ensure_ascii=False),
                    "created_at": finished_at,
                },
            )
            await log_db.commit()
    except Exception:
        logger.exception("Unable to persist scheduled transfer execution log schedule_id=%s", item.schedule_id)


def _normalize_receiver_identifier(identifier: str) -> tuple[str, str, str]:
    raw = " ".join(str(identifier or "").strip().split())
    normalized = raw.lower()
    paytag = normalized if normalized.startswith("@") else f"@{normalized}"
    return raw, normalized, paytag


async def _resolve_receiver(db: AsyncSession, identifier: str) -> Users:
    raw, normalized, paytag = _normalize_receiver_identifier(identifier)
    if not normalized:
        raise HTTPException(status_code=400, detail="Destinataire manquant")
    receiver = await db.scalar(
        select(Users).where(
            or_(
                func.lower(Users.email) == normalized,
                func.lower(Users.username) == normalized,
                func.lower(Users.paytag) == paytag,
                Users.phone_e164 == raw,
            )
        )
    )
    if not receiver:
        raise HTTPException(status_code=404, detail="Destinataire introuvable")
    return receiver


async def _execute_internal_transfer(
    db: AsyncSession,
    *,
    sender: Users,
    receiver_identifier: str,
    amount: Decimal,
    note: str | None = None,
    schedule_id: UUID | None = None,
) -> dict:
    receiver = await _resolve_receiver(db, receiver_identifier)
    if receiver.user_id == sender.user_id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas vous envoyer a vous-meme")

    sender_wallet = await db.scalar(_primary_wallet_stmt(sender.user_id))
    receiver_wallet = await db.scalar(_primary_wallet_stmt(receiver.user_id))
    if not sender_wallet or not receiver_wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    if str(sender_wallet.currency_code or "").upper() != str(receiver_wallet.currency_code or "").upper():
        raise HTTPException(status_code=400, detail="Transfert interne impossible entre devises differentes.")
    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == sender.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
        .with_for_update()
    )
    credit_line_currency = str(getattr(credit_line, "currency_code", "") or "").upper()
    sender_currency = str(sender_wallet.currency_code or "").upper()
    if credit_line and credit_line_currency and credit_line_currency != sender_currency:
        raise HTTPException(
            status_code=400,
            detail="Devise incoherente entre portefeuille et ligne de credit.",
        )
    credit_available = (
        max(Decimal(str(credit_line.outstanding_amount or 0)), Decimal("0"))
        if credit_line
        else max(
            Decimal(str(getattr(sender, "credit_limit", 0) or 0))
            - Decimal(str(getattr(sender, "credit_used", 0) or 0)),
            Decimal("0"),
        )
    )
    funding = compute_external_transfer_funding(
        wallet_available=Decimal(str(sender_wallet.available or 0)),
        credit_available=credit_available,
        total_required=amount,
        mirror_wallet_with_credit=True,
    )
    if funding["residual_after_credit"] > 0:
        raise HTTPException(status_code=400, detail="Solde insuffisant")

    sender_wallet.available = funding["wallet_after"]
    receiver_wallet.available = Decimal(str(receiver_wallet.available or 0)) + amount
    credit_used = funding["credit_used"]
    if credit_used > 0:
        if credit_line:
            credit_line.used_amount = Decimal(str(credit_line.used_amount or 0)) + credit_used
            credit_line.outstanding_amount = max(Decimal("0"), funding["credit_available_after"])
            credit_line.updated_at = _utcnow()
            sender.credit_limit = Decimal(str(credit_line.initial_amount or 0))
            sender.credit_used = Decimal(str(credit_line.used_amount or 0))
        else:
            sender.credit_used = Decimal(str(getattr(sender, "credit_used", 0) or 0)) + credit_used

    sender_movement = await log_wallet_movement(
        db,
        wallet=sender_wallet,
        user_id=sender.user_id,
        amount=amount,
        direction="debit",
        operation_type="scheduled_transfer_send" if schedule_id else "transfer_send",
        reference=receiver.email or receiver.paytag,
        description=note or f"Transfert programme vers {receiver.email or receiver.paytag}",
    )
    receiver_movement = await log_wallet_movement(
        db,
        wallet=receiver_wallet,
        user_id=receiver.user_id,
        amount=amount,
        direction="credit",
        operation_type="scheduled_transfer_receive" if schedule_id else "transfer_receive",
        reference=sender.email or sender.paytag,
        description=note or f"Transfert programme de {sender.email or sender.paytag}",
    )

    tx = Transactions(
        initiated_by=sender.user_id,
        sender_wallet=sender_wallet.wallet_id,
        receiver_wallet=receiver_wallet.wallet_id,
        amount=amount,
        currency_code=sender_wallet.currency_code,
        channel="internal",
        status="succeeded",
        description=note or f"Transfert programme vers {receiver.email or receiver.paytag}",
    )
    db.add(tx)
    await db.flush()

    ledger = LedgerService(db)
    sender_account = await ledger.ensure_wallet_account(sender_wallet)
    receiver_account = await ledger.ensure_wallet_account(receiver_wallet)
    metadata = {
        "operation": "scheduled_internal_transfer" if schedule_id else "internal_transfer",
        "sender_wallet_id": str(sender_wallet.wallet_id),
        "receiver_wallet_id": str(receiver_wallet.wallet_id),
        "sender_user_id": str(sender.user_id),
        "receiver_user_id": str(receiver.user_id),
        "transaction_id": str(tx.tx_id),
        "receiver_identifier": receiver_identifier,
        "credit_used_amount": str(credit_used),
        "credit_available_after": str(funding["credit_available_after"]),
    }
    if schedule_id:
        metadata["schedule_id"] = str(schedule_id)
    if sender_movement:
        metadata["sender_movement_id"] = str(sender_movement.transaction_id)
    if receiver_movement:
        metadata["receiver_movement_id"] = str(receiver_movement.transaction_id)
    await ledger.post_journal(
        tx_id=tx.tx_id,
        description=note or f"Transfert programme vers {receiver.email or receiver.paytag}",
        metadata=metadata,
        entries=[
            LedgerLine(
                account=sender_account,
                direction="debit",
                amount=amount,
                currency_code=sender_wallet.currency_code,
            ),
            LedgerLine(
                account=receiver_account,
                direction="credit",
                amount=amount,
                currency_code=receiver_wallet.currency_code,
            ),
        ],
    )
    return {
        "receiver_user_id": receiver.user_id,
        "currency_code": str(sender_wallet.currency_code or "").upper(),
        "tx_id": tx.tx_id,
        "credit_used": credit_used,
        "credit_available_after": funding["credit_available_after"],
    }


async def _execute_external_transfer(
    db: AsyncSession,
    *,
    sender: Users,
    item: ScheduledTransfers,
) -> dict:
    from app.routers.wallet.transfer import _external_transfer_core

    payload_data = _schedule_external_payload(item)
    if not payload_data:
        raise HTTPException(status_code=400, detail="Configuration du transfert externe manquante")

    try:
        payload = ExternalTransferCreate(
            partner_name=payload_data.get("partner_name"),
            country_destination=payload_data.get("country_destination"),
            recipient_name=payload_data.get("recipient_name"),
            recipient_phone=payload_data.get("recipient_phone"),
            recipient_email=payload_data.get("recipient_email"),
            amount=Decimal(str(item.amount)),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Configuration du transfert externe invalide") from exc

    background_tasks = BackgroundTasks()
    return await _external_transfer_core(
        data=payload,
        background_tasks=background_tasks,
        idempotency_key=None,
        db=db,
        current_user=sender,
        execute_notifications_inline=True,
    )


async def _run_scheduled_transfer_item(
    db: AsyncSession,
    *,
    current_user: Users,
    item: ScheduledTransfers,
    raise_on_failure: bool,
) -> dict:
    execution_started_at = _utcnow()
    try:
        metadata = _schedule_metadata(item)
        metadata["failure_count"] = 0
        previous_last_run_at = item.last_run_at
        monthly_anchor_day = metadata.get("monthly_anchor_day")
        if item.frequency == "monthly" and monthly_anchor_day is None:
            if previous_last_run_at is not None:
                monthly_anchor_day = previous_last_run_at.day
            elif item.next_run_at is not None:
                monthly_anchor_day = item.next_run_at.day
            metadata["monthly_anchor_day"] = monthly_anchor_day
            item.metadata_ = metadata
        transfer_type = _schedule_transfer_type(item)
        if transfer_type == "external":
            result = await _execute_external_transfer(
                db,
                sender=current_user,
                item=item,
            )
        else:
            result = await _execute_internal_transfer(
                db,
                sender=current_user,
                receiver_identifier=item.receiver_identifier,
                amount=Decimal(str(item.amount)),
                note=item.note,
                schedule_id=item.schedule_id,
            )
        now = _utcnow()
        item.status = "active"
        item.last_run_at = now
        item.updated_at = now
        if transfer_type == "external":
            reference_code = str(result.get("reference_code") or result.get("transfer_id") or "").strip()
            item.last_result = (
                f"Transfert externe planifie: {result.get('status', 'created')}"
                f"{f' ({reference_code})' if reference_code else ''}"
            )
            item.receiver_user_id = None
            item.currency_code = str(result.get("currency") or item.currency_code or "").upper() or item.currency_code
        else:
            item.last_result = "Execution reussie"
            item.receiver_user_id = result["receiver_user_id"]
            item.currency_code = result["currency_code"]
        if item.remaining_runs is not None:
            item.remaining_runs = max(int(item.remaining_runs) - 1, 0)
            if item.remaining_runs == 0:
                item.status = "completed"
                item.next_run_at = now
            else:
                item.next_run_at = _advance_next_run(
                    item.next_run_at,
                    item.frequency,
                    monthly_anchor_day=monthly_anchor_day,
                )
        else:
            item.next_run_at = _advance_next_run(
                item.next_run_at,
                item.frequency,
                monthly_anchor_day=monthly_anchor_day,
            )
        item.metadata_ = metadata
        await db.commit()
        await db.refresh(item)
        _log_scheduled_transfer_outcome(
            item,
            succeeded=True,
            reason=str(item.last_result or "Execution reussie"),
        )
        await _persist_scheduled_transfer_execution(
            item, succeeded=True, reason=str(item.last_result or "Execution reussie"),
            started_at=execution_started_at, details={"result": result},
        )
        return _serialize_schedule(item)
    except HTTPException as exc:
        metadata = _schedule_metadata(item)
        failure_count = _schedule_failure_count(item) + 1
        max_consecutive_failures = _schedule_max_consecutive_failures(item)
        metadata["failure_count"] = failure_count

        if failure_count >= max_consecutive_failures:
            item.status = "paused"
            item.last_result = f"{str(exc.detail)} | Mise en pause auto apres {failure_count} echecs consecutifs."
        else:
            item.status = "failed"
            item.last_result = str(exc.detail)
        item.metadata_ = metadata
        item.updated_at = _utcnow()
        _log_scheduled_transfer_outcome(
            item,
            succeeded=False,
            reason=str(item.last_result or exc.detail),
        )
        await db.commit()
        await db.refresh(item)
        await _persist_scheduled_transfer_execution(
            item, succeeded=False, reason=str(item.last_result or exc.detail),
            started_at=execution_started_at, error=exc,
        )
        if raise_on_failure:
            raise
        return _serialize_schedule(item)
    except ValueError as exc:
        metadata = _schedule_metadata(item)
        failure_count = _schedule_failure_count(item) + 1
        max_consecutive_failures = _schedule_max_consecutive_failures(item)
        metadata["failure_count"] = failure_count

        message = str(exc).strip() or "Erreur de validation planification"
        if failure_count >= max_consecutive_failures:
            item.status = "paused"
            item.last_result = f"{message} | Mise en pause auto apres {failure_count} echecs consecutifs."
        else:
            item.status = "failed"
            item.last_result = message
        item.metadata_ = metadata
        item.updated_at = _utcnow()
        _log_scheduled_transfer_outcome(
            item,
            succeeded=False,
            reason=str(item.last_result or message),
            exc_info=True,
        )
        await db.commit()
        await db.refresh(item)
        await _persist_scheduled_transfer_execution(
            item, succeeded=False, reason=str(item.last_result or message),
            started_at=execution_started_at, error=exc,
        )
        if raise_on_failure:
            raise HTTPException(
                status_code=500,
                detail="Execution du transfert programme impossible pour le moment.",
            ) from exc
        return _serialize_schedule(item)
    except Exception as exc:
        metadata = _schedule_metadata(item)
        failure_count = _schedule_failure_count(item) + 1
        max_consecutive_failures = _schedule_max_consecutive_failures(item)
        metadata["failure_count"] = failure_count

        message = f"Erreur technique planification ({exc.__class__.__name__})"
        if failure_count >= max_consecutive_failures:
            item.status = "paused"
            item.last_result = f"{message} | Mise en pause auto apres {failure_count} echecs consecutifs."
        else:
            item.status = "failed"
            item.last_result = message
        item.metadata_ = metadata
        item.updated_at = _utcnow()
        _log_scheduled_transfer_outcome(
            item,
            succeeded=False,
            reason=str(item.last_result or message),
            exc_info=True,
        )
        await db.commit()
        await db.refresh(item)
        await _persist_scheduled_transfer_execution(
            item, succeeded=False, reason=str(item.last_result or message),
            started_at=execution_started_at, error=exc,
        )
        if raise_on_failure:
            raise HTTPException(
                status_code=500,
                detail="Execution du transfert programme impossible pour le moment.",
            ) from exc
        return _serialize_schedule(item)


async def create_scheduled_transfer(
    db: AsyncSession,
    *,
    current_user: Users,
    payload,
):
    next_run_at = payload.next_run_at
    if next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=timezone.utc)
    if next_run_at < _utcnow():
        raise HTTPException(status_code=400, detail="La prochaine execution doit etre dans le futur")

    sender_wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not sender_wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    receiver_user_id = None
    receiver_identifier = ""
    metadata: dict = {
        "transfer_type": payload.transfer_type,
        "failure_count": 0,
        "max_consecutive_failures": int(payload.max_consecutive_failures),
    }
    if payload.frequency == "monthly":
        metadata["monthly_anchor_day"] = next_run_at.day
    if payload.transfer_type == "external":
        external_transfer = payload.external_transfer.model_dump(mode="json", exclude_none=True)
        receiver_identifier = (
            str(payload.external_transfer.recipient_phone or "").strip()
            or str(payload.external_transfer.recipient_name or "").strip()
        )
        metadata["external_transfer"] = external_transfer
    else:
        receiver = await _resolve_receiver(db, payload.receiver_identifier)
        if receiver.user_id == current_user.user_id:
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas vous envoyer a vous-meme")
        receiver_wallet = await db.scalar(_primary_wallet_stmt(receiver.user_id))
        if not receiver_wallet:
            raise HTTPException(status_code=404, detail="Portefeuille introuvable")
        if str(sender_wallet.currency_code or "").upper() != str(receiver_wallet.currency_code or "").upper():
            raise HTTPException(status_code=400, detail="Transfert programme impossible entre devises differentes.")
        receiver_user_id = receiver.user_id
        receiver_identifier = (
            str(receiver.paytag or "").strip()
            or str(receiver.email or "").strip().lower()
            or str(receiver.username or "").strip()
            or str(receiver.phone_e164 or "").strip()
        )

    item = ScheduledTransfers(
        user_id=current_user.user_id,
        receiver_user_id=receiver_user_id,
        receiver_identifier=receiver_identifier,
        amount=payload.amount,
        currency_code=str(sender_wallet.currency_code or "").upper(),
        frequency=payload.frequency,
        status="active",
        note=payload.note,
        next_run_at=next_run_at,
        remaining_runs=payload.remaining_runs,
        metadata_=metadata,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def update_scheduled_transfer(
    db: AsyncSession,
    *,
    current_user: Users,
    schedule_id: UUID,
    payload,
):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    if item.status in {"cancelled", "completed"}:
        raise HTTPException(status_code=400, detail="Ce transfert programme ne peut pas etre modifie")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return _serialize_schedule(item)

    now = _utcnow()
    metadata = _schedule_metadata(item)

    next_run_at = updates.get("next_run_at")
    if next_run_at is not None:
        if next_run_at.tzinfo is None:
            next_run_at = next_run_at.replace(tzinfo=timezone.utc)
        if next_run_at < now:
            raise HTTPException(status_code=400, detail="La prochaine execution doit etre dans le futur")
        item.next_run_at = next_run_at

    if "amount" in updates and updates.get("amount") is not None:
        item.amount = updates["amount"]
    if "frequency" in updates and updates.get("frequency") is not None:
        item.frequency = updates["frequency"]
    if "note" in updates:
        item.note = updates.get("note")
    if "remaining_runs" in updates:
        item.remaining_runs = updates.get("remaining_runs")

    if "max_consecutive_failures" in updates and updates.get("max_consecutive_failures") is not None:
        metadata["max_consecutive_failures"] = int(updates["max_consecutive_failures"])

    monthly_anchor = None
    if item.frequency == "monthly":
        anchor_source = item.next_run_at or next_run_at
        if anchor_source is not None:
            monthly_anchor = anchor_source.day
            metadata["monthly_anchor_day"] = monthly_anchor
    else:
        metadata.pop("monthly_anchor_day", None)

    metadata["failure_count"] = 0
    item.metadata_ = metadata
    item.updated_at = now
    item.last_result = "Programmation modifiee par l'utilisateur"
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def list_scheduled_transfers(db: AsyncSession, *, current_user: Users):
    rows = (
        await db.execute(
            select(ScheduledTransfers)
            .where(ScheduledTransfers.user_id == current_user.user_id)
            .order_by(ScheduledTransfers.created_at.desc())
        )
    ).scalars().all()
    return [_serialize_schedule(item) for item in rows]


async def get_scheduled_transfer_diagnostic(
    db: AsyncSession,
    *,
    current_user: Users,
    schedule_id: UUID,
) -> dict:
    item = await db.scalar(
        select(ScheduledTransfers).where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")

    payload = _serialize_schedule(item)
    transfer_type = _schedule_transfer_type(item)
    metadata = _schedule_metadata(item)
    diagnostic = {
        "schedule_id": str(item.schedule_id),
        "transfer_type": transfer_type,
        "status": payload["status"],
        "is_due": payload["is_due"],
        "failure_count": payload["failure_count"],
        "max_consecutive_failures": payload["max_consecutive_failures"],
        "last_result": payload["last_result"],
        "next_run_at": payload["next_run_at"],
        "recommended_action": _scheduled_transfer_recommended_action(item, transfer_type=transfer_type),
        "blocking_reasons": [],
        "context": {},
    }

    if transfer_type != "external":
        return diagnostic

    external_payload = _schedule_external_payload(item) or {}
    partner_name = str(external_payload.get("partner_name") or "").strip()
    recipient_phone = str(external_payload.get("recipient_phone") or "").strip()
    recipient_name = str(external_payload.get("recipient_name") or "").strip()
    country_destination = str(external_payload.get("country_destination") or "").strip()

    latest_transfer = await db.scalar(
        select(ExternalTransfers)
        .where(
            ExternalTransfers.user_id == current_user.user_id,
            ExternalTransfers.partner_name == partner_name,
            ExternalTransfers.country_destination == country_destination,
            ExternalTransfers.recipient_phone == recipient_phone,
            ExternalTransfers.recipient_name == recipient_name,
        )
        .order_by(ExternalTransfers.created_at.desc())
        .limit(1)
    )

    if latest_transfer:
        transfer_metadata = dict(getattr(latest_transfer, "metadata_", {}) or {})
        funding_pending = bool(transfer_metadata.get("funding_pending"))
        aml_manual = bool(transfer_metadata.get("aml_manual_review_required"))
        required_credit_topup = transfer_metadata.get("required_credit_topup")
        review_reasons = list(transfer_metadata.get("review_reasons") or [])
        aml_reason_codes = list(transfer_metadata.get("aml_reason_codes") or [])

        if funding_pending:
            diagnostic["blocking_reasons"].append("funding_pending")
        if aml_manual:
            diagnostic["blocking_reasons"].append("aml_manual_review_required")
        if str(getattr(latest_transfer, "status", "") or "").strip().lower() == "pending":
            diagnostic["blocking_reasons"].append("external_transfer_pending_approval")

        diagnostic["context"] = {
            "external_transfer_id": str(latest_transfer.transfer_id),
            "external_transfer_reference": latest_transfer.reference_code,
            "external_transfer_status": latest_transfer.status,
            "amount": str(latest_transfer.amount),
            "fee_amount": transfer_metadata.get("fee_amount"),
            "total_required": transfer_metadata.get("total_required"),
            "required_credit_topup": required_credit_topup,
            "review_reasons": review_reasons,
            "aml_reason_codes": aml_reason_codes,
            "funding_pending": funding_pending,
            "aml_manual_review_required": aml_manual,
        }
    else:
        diagnostic["blocking_reasons"].append("no_external_attempt_found")
        diagnostic["context"] = {
            "partner_name": partner_name,
            "recipient_phone": recipient_phone,
            "country_destination": country_destination,
        }

    return diagnostic


async def pause_scheduled_transfer(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    if item.status in {"cancelled", "completed"}:
        raise HTTPException(status_code=400, detail="Ce transfert programme ne peut pas etre mis en pause")
    item.status = "paused"
    item.updated_at = _utcnow()
    item.last_result = "Mis en pause par l'utilisateur"
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def resume_scheduled_transfer(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    if item.status != "paused":
        raise HTTPException(status_code=400, detail="Ce transfert programme n'est pas en pause")
    now = _utcnow()
    metadata = _schedule_metadata(item)
    metadata["failure_count"] = 0
    item.status = "active"
    item.updated_at = now
    item.last_result = "Repris par l'utilisateur"
    item.metadata_ = metadata
    if item.next_run_at and item.next_run_at < now:
        item.next_run_at = now
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def cancel_scheduled_transfer(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    item.status = "cancelled"
    item.updated_at = _utcnow()
    item.last_result = "Annule par l'utilisateur"
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def run_due_scheduled_transfers(db: AsyncSession, *, current_user: Users):
    rows = (
        await db.execute(
            select(ScheduledTransfers)
            .where(
                ScheduledTransfers.user_id == current_user.user_id,
                ScheduledTransfers.status.in_(("active", "failed")),
                ScheduledTransfers.next_run_at <= _utcnow(),
            )
            .order_by(ScheduledTransfers.next_run_at.asc())
            .with_for_update()
        )
    ).scalars().all()
    processed = []
    for item in rows:
        processed.append(
            await _run_scheduled_transfer_item(
                db,
                current_user=current_user,
                item=item,
                raise_on_failure=False,
            )
        )
    return processed


async def run_scheduled_transfer_now(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    if item.status not in {"active", "failed"}:
        raise HTTPException(status_code=400, detail="Ce transfert programme ne peut pas etre execute")
    return await _run_scheduled_transfer_item(
        db,
        current_user=current_user,
        item=item,
        raise_on_failure=True,
    )


async def run_global_due_scheduled_transfers(db: AsyncSession, *, limit: int = 100) -> dict:
    rows = (
        await db.execute(
            select(ScheduledTransfers)
            .where(
                ScheduledTransfers.status.in_(("active", "failed")),
                ScheduledTransfers.next_run_at <= _utcnow(),
            )
            .order_by(ScheduledTransfers.next_run_at.asc(), ScheduledTransfers.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    if not rows:
        return {"processed": 0, "succeeded": 0, "failed": 0}

    users = {
        item.user_id: item
        for item in (
            await db.execute(select(Users).where(Users.user_id.in_([row.user_id for row in rows])))
        ).scalars().all()
    }

    processed = 0
    succeeded = 0
    failed = 0
    for item in rows:
        current_user = users.get(item.user_id)
        if not current_user:
            item.status = "failed"
            item.updated_at = _utcnow()
            item.last_result = "Utilisateur emetteur introuvable"
            await db.commit()
            processed += 1
            failed += 1
            continue
        result = await _run_scheduled_transfer_item(
            db,
            current_user=current_user,
            item=item,
            raise_on_failure=False,
        )
        processed += 1
        if result["status"] in {"active", "completed"}:
            succeeded += 1
        else:
            failed += 1

    return {"processed": processed, "succeeded": succeeded, "failed": failed}

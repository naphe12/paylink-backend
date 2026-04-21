from __future__ import annotations

import decimal
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.credit_lines import CreditLines
from app.models.external_transfers import ExternalTransfers
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_transactions import WalletEntryDirectionEnum
from app.models.wallets import Wallets
from app.services.external_transfer_provider import (
    PROVIDER_STATUS_FAILED,
    PROVIDER_STATUS_MANUAL_REVIEW,
    PROVIDER_STATUS_PROCESSING,
    PROVIDER_STATUS_RETRY,
    PROVIDER_STATUS_SENT,
    PROVIDER_STATUS_SUCCESS,
    ExternalTransferProviderError,
    ExternalTransferProviderTimeout,
    get_external_transfer_provider,
    normalize_provider_status,
)
from app.services.ledger import LedgerLine, LedgerService
from app.services.external_transfer_rules import (
    map_external_transfer_to_transaction_status,
    transition_external_transfer_status,
)
from app.services.wallet_history import log_wallet_movement

DISPATCHABLE_TRANSFER_STATUSES = {"approved"}
POLLABLE_PROVIDER_STATUSES = {PROVIDER_STATUS_SENT, PROVIDER_STATUS_PROCESSING, PROVIDER_STATUS_RETRY}
ZERO = decimal.Decimal("0")


def _resolve_provider_name(transfer: ExternalTransfers) -> str:
    explicit = str(getattr(transfer, "provider", "") or "").strip().lower()
    if explicit and explicit != "internal":
        return explicit

    partner = str(getattr(transfer, "partner_name", "") or "").strip().lower()
    if "ihela" in partner:
        return "ihela"

    default_provider = str(getattr(settings, "EXTERNAL_TRANSFER_PROVIDER_DEFAULT", "internal") or "internal").strip().lower()
    return default_provider or "internal"


def _serialize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {"raw": str(payload)}


def _next_retry_at(retry_count: int) -> datetime:
    base_seconds = max(int(getattr(settings, "EXTERNAL_TRANSFER_PROVIDER_BACKOFF_BASE_SECONDS", 30) or 30), 1)
    delay = base_seconds * (2 ** max(retry_count - 1, 0))
    return datetime.now(UTC) + timedelta(seconds=delay)


def _can_retry(transfer: ExternalTransfers) -> bool:
    max_retry = max(int(getattr(settings, "EXTERNAL_TRANSFER_PROVIDER_RETRY_MAX", 3) or 3), 0)
    return int(getattr(transfer, "retry_count", 0) or 0) < max_retry


def _should_dispatch_now(transfer: ExternalTransfers) -> bool:
    if str(getattr(transfer, "status", "") or "").strip().lower() not in DISPATCHABLE_TRANSFER_STATUSES:
        return False
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    next_retry_raw = metadata.get("provider_next_retry_at")
    if not next_retry_raw:
        return True
    try:
        next_retry_at = datetime.fromisoformat(str(next_retry_raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(UTC) >= next_retry_at.astimezone(UTC)


def _mark_provider_state(
    transfer: ExternalTransfers,
    *,
    provider: str,
    provider_status: str,
    provider_ref: str | None = None,
    last_error: str | None = None,
    provider_payload: dict[str, Any] | None = None,
    increment_retry: bool = False,
) -> None:
    transfer.provider = provider
    transfer.provider_status = provider_status
    if provider_ref:
        transfer.provider_ref = provider_ref
    transfer.last_error = last_error
    if increment_retry:
        transfer.retry_count = int(getattr(transfer, "retry_count", 0) or 0) + 1
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    if provider_payload is not None:
        metadata["provider_last_payload"] = provider_payload
    if last_error:
        metadata["provider_last_error"] = last_error
    if provider_status == PROVIDER_STATUS_RETRY:
        metadata["provider_next_retry_at"] = _next_retry_at(int(transfer.retry_count or 0)).isoformat()
    else:
        metadata.pop("provider_next_retry_at", None)
    transfer.metadata_ = metadata


def _sync_transaction_status(transfer: ExternalTransfers, txn: Transactions | None) -> None:
    if not txn:
        return
    txn.status = map_external_transfer_to_transaction_status(transfer.status)
    txn.updated_at = datetime.utcnow()


def _safe_decimal(value: Any, default: decimal.Decimal = ZERO) -> decimal.Decimal:
    try:
        return decimal.Decimal(str(value))
    except Exception:
        return default


async def _apply_failed_refund(
    db: AsyncSession,
    *,
    transfer: ExternalTransfers,
    txn: Transactions | None,
) -> None:
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    if bool(metadata.get("provider_refund_done")):
        return

    total_required = _safe_decimal(metadata.get("total_required"))
    wallet_refund_amount = _safe_decimal(metadata.get("debited_amount"))
    credit_used_amount = _safe_decimal(metadata.get("credit_used_amount"))
    wallet_id = str(metadata.get("wallet_id") or "").strip()

    if total_required <= ZERO and wallet_refund_amount <= ZERO and credit_used_amount <= ZERO:
        metadata["provider_refund_done"] = True
        metadata["provider_refund_reason"] = "nothing_to_refund"
        transfer.metadata_ = metadata
        return

    wallet_stmt = select(Wallets).where(Wallets.wallet_id == wallet_id).with_for_update() if wallet_id else None
    wallet = await db.scalar(wallet_stmt) if wallet_stmt is not None else None
    if not wallet:
        wallet = await db.scalar(
            select(Wallets)
            .where(Wallets.user_id == transfer.user_id)
            .order_by(Wallets.wallet_id.asc())
            .limit(1)
            .with_for_update()
        )
    if not wallet:
        raise RuntimeError(f"Wallet introuvable pour refund transfert {transfer.transfer_id}")

    if wallet_refund_amount > ZERO:
        wallet.available = _safe_decimal(wallet.available) + wallet_refund_amount
        movement = await log_wallet_movement(
            db,
            wallet=wallet,
            user_id=transfer.user_id,
            amount=wallet_refund_amount,
            direction=WalletEntryDirectionEnum.CREDIT,
            operation_type="external_transfer_provider_refund",
            reference=str(transfer.reference_code or transfer.transfer_id),
            description=f"Remboursement automatique transfert externe {transfer.reference_code or transfer.transfer_id}",
        )
        if movement:
            metadata["provider_refund_wallet_movement_id"] = str(movement.transaction_id)

    user_locked = await db.scalar(
        select(Users).where(Users.user_id == transfer.user_id).with_for_update()
    )

    if credit_used_amount > ZERO:
        credit_line = await db.scalar(
            select(CreditLines)
            .where(
                CreditLines.user_id == transfer.user_id,
                CreditLines.deleted_at.is_(None),
                CreditLines.status == "active",
            )
            .order_by(CreditLines.created_at.desc())
            .with_for_update()
        )
        if credit_line:
            used_before = _safe_decimal(credit_line.used_amount)
            available_before = _safe_decimal(credit_line.outstanding_amount)
            initial_limit = _safe_decimal(credit_line.initial_amount)
            credit_line.used_amount = max(ZERO, used_before - credit_used_amount)
            credit_line.outstanding_amount = min(
                initial_limit if initial_limit > ZERO else available_before + credit_used_amount,
                max(ZERO, available_before + credit_used_amount),
            )
            credit_line.updated_at = datetime.utcnow()
            if user_locked:
                user_locked.credit_limit = _safe_decimal(credit_line.initial_amount)
                user_locked.credit_used = _safe_decimal(credit_line.used_amount)
        elif user_locked:
            user_locked.credit_used = max(ZERO, _safe_decimal(user_locked.credit_used) - credit_used_amount)

    ledger = LedgerService(db)
    sender_account = await ledger.ensure_wallet_account(wallet)
    cash_out_account = await ledger.get_cash_out_account(wallet.currency_code)
    entries: list[LedgerLine] = []
    if wallet_refund_amount > ZERO:
        entries.append(
            LedgerLine(
                account=sender_account,
                direction="credit",
                amount=wallet_refund_amount,
                currency_code=wallet.currency_code,
            )
        )
    if credit_used_amount > ZERO:
        credit_account = await ledger.ensure_system_account(
            code=settings.LEDGER_ACCOUNT_CREDIT_LINE,
            name="Ligne de credit clients",
            currency_code=wallet.currency_code,
            metadata={"kind": "system", "purpose": "credit_line"},
        )
        entries.append(
            LedgerLine(
                account=credit_account,
                direction="credit",
                amount=credit_used_amount,
                currency_code=wallet.currency_code,
            )
        )
    if total_required > ZERO:
        entries.append(
            LedgerLine(
                account=cash_out_account,
                direction="debit",
                amount=total_required,
                currency_code=wallet.currency_code,
            )
        )

    if entries:
        refund_tx_id = UUID(str(getattr(txn, "tx_id", transfer.transfer_id)))
        await ledger.post_journal(
            tx_id=refund_tx_id,
            description=f"Remboursement provider failed {transfer.reference_code or transfer.transfer_id}",
            metadata={
                "operation": "external_transfer_provider_refund",
                "transfer_id": str(transfer.transfer_id),
                "reference_code": str(transfer.reference_code or ""),
                "wallet_refund_amount": str(wallet_refund_amount),
                "credit_refund_amount": str(credit_used_amount),
                "total_required": str(total_required),
                "provider": str(getattr(transfer, "provider", "") or ""),
            },
            entries=entries,
        )

    metadata["provider_refund_done"] = True
    metadata["provider_refund_at"] = datetime.utcnow().isoformat()
    metadata["provider_refund_wallet_amount"] = str(wallet_refund_amount)
    metadata["provider_refund_credit_amount"] = str(credit_used_amount)
    metadata["credit_used_amount"] = "0"
    metadata["credit_repaid_amount"] = "0.00"
    metadata["credit_outstanding_amount"] = "0"
    metadata["credit_repayment_status"] = "no_credit_debt"
    transfer.metadata_ = metadata


def _apply_terminal_mapping(
    transfer: ExternalTransfers,
    txn: Transactions | None,
    *,
    provider_status: str,
) -> None:
    if provider_status == PROVIDER_STATUS_SUCCESS:
        try:
            transition_external_transfer_status(transfer, "succeeded")
        except ValueError:
            transfer.status = "succeeded"
        _sync_transaction_status(transfer, txn)


async def _apply_terminal_mapping_async(
    db: AsyncSession,
    transfer: ExternalTransfers,
    txn: Transactions | None,
    *,
    provider_status: str,
) -> None:
    if provider_status == PROVIDER_STATUS_SUCCESS:
        _apply_terminal_mapping(transfer, txn, provider_status=provider_status)
        return
    if provider_status == PROVIDER_STATUS_FAILED:
        await _apply_failed_refund(db, transfer=transfer, txn=txn)
        try:
            transition_external_transfer_status(transfer, "failed")
        except ValueError:
            transfer.status = "failed"
        _sync_transaction_status(transfer, txn)


async def _dispatch_provider_for_transfer(
    db: AsyncSession,
    *,
    transfer: ExternalTransfers,
) -> dict[str, Any]:
    provider_name = _resolve_provider_name(transfer)
    if provider_name in {"", "internal", "none"}:
        _mark_provider_state(
            transfer,
            provider="internal",
            provider_status="created",
            last_error=None,
        )
        return {"status": "SKIPPED", "reason": "internal_provider"}

    if not _should_dispatch_now(transfer):
        return {"status": "SKIPPED", "reason": "retry_backoff"}

    if str(getattr(transfer, "status", "") or "").strip().lower() not in DISPATCHABLE_TRANSFER_STATUSES:
        return {"status": "SKIPPED", "reason": "status_not_dispatchable"}

    txn = await db.scalar(select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id))
    metadata = dict(getattr(transfer, "metadata_", {}) or {})
    idempotency_key = str(getattr(transfer, "idempotency_key", "") or "").strip() or f"ext-{transfer.transfer_id}"
    transfer.idempotency_key = idempotency_key
    _mark_provider_state(
        transfer,
        provider=provider_name,
        provider_status=PROVIDER_STATUS_PROCESSING,
    )

    amount = str(getattr(transfer, "amount", "0"))
    currency = str(metadata.get("origin_currency") or getattr(transfer, "currency", "EUR") or "EUR").upper()
    recipient_name = str(getattr(transfer, "recipient_name", "") or "").strip() or None
    reference = str(getattr(transfer, "reference_code", "") or transfer.transfer_id)

    try:
        provider = get_external_transfer_provider(provider_name)
        send_result = await provider.send(
            transfer_id=transfer.transfer_id,
            amount=amount,
            currency=currency,
            recipient_phone=str(getattr(transfer, "recipient_phone", "") or ""),
            recipient_name=recipient_name,
            reference=reference,
            idempotency_key=idempotency_key,
        )
        normalized_provider_status = normalize_provider_status(send_result.provider_status)
        _mark_provider_state(
            transfer,
            provider=provider_name,
            provider_status=normalized_provider_status,
            provider_ref=send_result.provider_ref,
            last_error=None,
            provider_payload=_serialize_payload(send_result.raw_response),
        )
        if normalized_provider_status in {PROVIDER_STATUS_SUCCESS, PROVIDER_STATUS_FAILED} or send_result.terminal:
            await _apply_terminal_mapping_async(
                db,
                transfer,
                txn,
                provider_status=normalized_provider_status,
            )
        return {
            "status": "DISPATCHED",
            "provider": provider_name,
            "provider_status": normalized_provider_status,
            "provider_ref": getattr(transfer, "provider_ref", None),
        }
    except ExternalTransferProviderTimeout as exc:
        if _can_retry(transfer):
            _mark_provider_state(
                transfer,
                provider=provider_name,
                provider_status=PROVIDER_STATUS_RETRY,
                last_error=str(exc),
                increment_retry=True,
            )
            return {"status": "RETRY", "reason": str(exc)}
        _mark_provider_state(
            transfer,
            provider=provider_name,
            provider_status=PROVIDER_STATUS_MANUAL_REVIEW,
            last_error=str(exc),
        )
        return {"status": "MANUAL_REVIEW", "reason": str(exc)}
    except ExternalTransferProviderError as exc:
        if getattr(exc, "retryable", False) and _can_retry(transfer):
            _mark_provider_state(
                transfer,
                provider=provider_name,
                provider_status=PROVIDER_STATUS_RETRY,
                last_error=str(exc),
                increment_retry=True,
            )
            return {"status": "RETRY", "reason": str(exc)}

        target_provider_status = PROVIDER_STATUS_MANUAL_REVIEW if getattr(exc, "retryable", False) else PROVIDER_STATUS_FAILED
        _mark_provider_state(
            transfer,
            provider=provider_name,
            provider_status=target_provider_status,
            last_error=str(exc),
        )
        if target_provider_status == PROVIDER_STATUS_FAILED:
            await _apply_terminal_mapping_async(
                db,
                transfer,
                txn,
                provider_status=PROVIDER_STATUS_FAILED,
            )
        return {"status": target_provider_status.upper(), "reason": str(exc)}


async def dispatch_external_transfer_provider_by_id(transfer_id: str | UUID) -> dict[str, Any]:
    async with async_session_maker() as db:
        transfer = await db.scalar(
            select(ExternalTransfers)
            .where(ExternalTransfers.transfer_id == UUID(str(transfer_id)))
            .with_for_update()
        )
        if not transfer:
            return {"status": "NOT_FOUND"}
        result = await _dispatch_provider_for_transfer(db, transfer=transfer)
        await db.commit()
        return result


async def apply_provider_status_update(
    db: AsyncSession,
    *,
    transfer: ExternalTransfers,
    provider_status: str,
    provider_ref: str | None = None,
    last_error: str | None = None,
    provider_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_provider = _resolve_provider_name(transfer)
    normalized_status = normalize_provider_status(provider_status)
    txn = await db.scalar(select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id))

    _mark_provider_state(
        transfer,
        provider=normalized_provider,
        provider_status=normalized_status,
        provider_ref=provider_ref,
        last_error=last_error,
        provider_payload=provider_payload,
    )
    if normalized_status in {PROVIDER_STATUS_SUCCESS, PROVIDER_STATUS_FAILED}:
        await _apply_terminal_mapping_async(
            db,
            transfer,
            txn,
            provider_status=normalized_status,
        )
    return {
        "status": "UPDATED",
        "provider_status": normalized_status,
        "transfer_status": str(getattr(transfer, "status", "") or "").lower(),
    }


async def reconcile_external_transfer_providers(limit: int | None = None) -> dict[str, Any]:
    safe_limit = max(int(limit or getattr(settings, "EXTERNAL_TRANSFER_PROVIDER_RECONCILE_BATCH_SIZE", 100) or 100), 1)
    summary = {"scanned": 0, "updated": 0, "skipped": 0, "errors": 0}

    async with async_session_maker() as db:
        stmt = (
            select(ExternalTransfers)
            .where(ExternalTransfers.provider_status.in_(tuple(POLLABLE_PROVIDER_STATUSES)))
            .order_by(ExternalTransfers.created_at.asc())
            .limit(safe_limit)
            .with_for_update()
        )
        transfers = (await db.execute(stmt)).scalars().all()
        summary["scanned"] = len(transfers)

        for transfer in transfers:
            provider_name = _resolve_provider_name(transfer)
            if provider_name in {"", "internal", "none"}:
                summary["skipped"] += 1
                continue

            provider_status = str(getattr(transfer, "provider_status", "") or "").strip().lower()
            provider_ref = str(getattr(transfer, "provider_ref", "") or "").strip() or None
            try:
                if provider_status == PROVIDER_STATUS_RETRY or not provider_ref:
                    result = await _dispatch_provider_for_transfer(db, transfer=transfer)
                    if result.get("status") in {"DISPATCHED", "RETRY", "MANUAL_REVIEW", "FAILED"}:
                        summary["updated"] += 1
                    else:
                        summary["skipped"] += 1
                    continue

                provider = get_external_transfer_provider(provider_name)
                status_result = await provider.get_status(provider_ref=provider_ref)
                update = await apply_provider_status_update(
                    db,
                    transfer=transfer,
                    provider_status=status_result.provider_status,
                    provider_ref=provider_ref,
                    provider_payload=_serialize_payload(status_result.raw_response),
                )
                if update.get("status") == "UPDATED":
                    summary["updated"] += 1
                else:
                    summary["skipped"] += 1
            except ExternalTransferProviderError as exc:
                if getattr(exc, "retryable", False) and _can_retry(transfer):
                    _mark_provider_state(
                        transfer,
                        provider=provider_name,
                        provider_status=PROVIDER_STATUS_RETRY,
                        last_error=str(exc),
                        increment_retry=True,
                    )
                    summary["updated"] += 1
                else:
                    _mark_provider_state(
                        transfer,
                        provider=provider_name,
                        provider_status=PROVIDER_STATUS_MANUAL_REVIEW,
                        last_error=str(exc),
                    )
                    summary["updated"] += 1
            except Exception as exc:  # pragma: no cover - safety net
                _mark_provider_state(
                    transfer,
                    provider=provider_name,
                    provider_status=PROVIDER_STATUS_MANUAL_REVIEW,
                    last_error=f"reconcile_error: {exc}",
                )
                summary["errors"] += 1

        await db.commit()
    return summary

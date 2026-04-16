from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_transfers import ExternalTransfers
from app.services.external_transfer_rules import (
    EXTERNAL_TRANSFER_STATUS_COMPLETED,
    EXTERNAL_TRANSFER_STATUS_PARTIALLY_REPAID,
    EXTERNAL_TRANSFER_STATUS_REPAID,
    EXTERNAL_TRANSFER_STATUS_SUCCEEDED,
    normalize_external_transfer_status,
    transition_external_transfer_status,
)


def _safe_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _serialize_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _can_override_transfer_status(current_status: str) -> bool:
    return current_status in {
        EXTERNAL_TRANSFER_STATUS_COMPLETED,
        EXTERNAL_TRANSFER_STATUS_SUCCEEDED,
        EXTERNAL_TRANSFER_STATUS_PARTIALLY_REPAID,
        EXTERNAL_TRANSFER_STATUS_REPAID,
    }


async def allocate_credit_repayment_to_external_transfers(
    db: AsyncSession,
    *,
    user_id,
    repayment_amount: Decimal,
    source: str,
    reference: str | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    amount_to_allocate = max(_safe_decimal(repayment_amount), Decimal("0"))
    if amount_to_allocate <= Decimal("0"):
        return {
            "total_repaid": Decimal("0"),
            "remaining_unallocated": Decimal("0"),
            "allocations": [],
        }

    now = occurred_at or datetime.utcnow()
    transfers = (
        await db.execute(
            select(ExternalTransfers)
            .where(
                ExternalTransfers.user_id == user_id,
                ExternalTransfers.credit_used.is_(True),
            )
            .order_by(ExternalTransfers.created_at.asc())
            .with_for_update()
        )
    ).scalars().all()

    allocations: list[dict] = []
    remaining = amount_to_allocate

    for transfer in transfers:
        if remaining <= Decimal("0"):
            break

        metadata = dict(getattr(transfer, "metadata_", {}) or {})
        original_credit_used = max(_safe_decimal(metadata.get("credit_used_amount")), Decimal("0"))
        if original_credit_used <= Decimal("0"):
            continue

        already_repaid = max(_safe_decimal(metadata.get("credit_repaid_amount")), Decimal("0"))
        outstanding_before = max(original_credit_used - already_repaid, Decimal("0"))
        if outstanding_before <= Decimal("0"):
            metadata["credit_repayment_status"] = "fully_repaid"
            metadata["credit_outstanding_amount"] = _serialize_decimal(Decimal("0"))
            transfer.metadata_ = metadata
            continue

        applied = min(outstanding_before, remaining)
        if applied <= Decimal("0"):
            continue

        new_repaid_total = already_repaid + applied
        outstanding_after = max(original_credit_used - new_repaid_total, Decimal("0"))
        repayment_status = "fully_repaid" if outstanding_after <= Decimal("0") else "partially_repaid"

        metadata["credit_used_amount"] = _serialize_decimal(original_credit_used)
        metadata["credit_repaid_amount"] = _serialize_decimal(new_repaid_total)
        metadata["credit_outstanding_amount"] = _serialize_decimal(outstanding_after)
        metadata["credit_repayment_status"] = repayment_status
        metadata["credit_repayment_updated_at"] = now.isoformat()
        history = list(metadata.get("credit_repayment_history") or [])
        history.append(
            {
                "at": now.isoformat(),
                "source": str(source or "").strip() or "unknown",
                "amount": _serialize_decimal(applied),
                "reference": reference,
            }
        )
        metadata["credit_repayment_history"] = history

        current_status = normalize_external_transfer_status(getattr(transfer, "status", None))
        if _can_override_transfer_status(current_status):
            if current_status in {EXTERNAL_TRANSFER_STATUS_COMPLETED, EXTERNAL_TRANSFER_STATUS_SUCCEEDED}:
                metadata.setdefault("settlement_status", current_status)
            target_status = (
                EXTERNAL_TRANSFER_STATUS_REPAID
                if outstanding_after <= Decimal("0")
                else EXTERNAL_TRANSFER_STATUS_PARTIALLY_REPAID
            )
            transition_external_transfer_status(transfer, target_status)

        transfer.metadata_ = metadata
        allocations.append(
            {
                "transfer_id": str(transfer.transfer_id),
                "reference_code": transfer.reference_code,
                "applied_amount": applied,
                "outstanding_before": outstanding_before,
                "outstanding_after": outstanding_after,
                "transfer_status": str(getattr(transfer, "status", "") or ""),
                "repayment_status": repayment_status,
            }
        )
        remaining -= applied

    return {
        "total_repaid": amount_to_allocate - remaining,
        "remaining_unallocated": remaining,
        "allocations": allocations,
    }


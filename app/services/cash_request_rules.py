from __future__ import annotations

from fastapi import HTTPException

from app.models.wallet_cash_requests import WalletCashRequestStatus, WalletCashRequests


ALLOWED_CASH_REQUEST_TRANSITIONS: dict[WalletCashRequestStatus, set[WalletCashRequestStatus]] = {
    WalletCashRequestStatus.PENDING: {
        WalletCashRequestStatus.APPROVED,
        WalletCashRequestStatus.REJECTED,
    },
    WalletCashRequestStatus.APPROVED: {
        WalletCashRequestStatus.COMPLETED,
    },
    WalletCashRequestStatus.REJECTED: set(),
    WalletCashRequestStatus.COMPLETED: set(),
}


def validate_cash_request_transition(
    from_status: WalletCashRequestStatus,
    to_status: WalletCashRequestStatus,
) -> None:
    if from_status == to_status:
        return
    allowed_targets = ALLOWED_CASH_REQUEST_TRANSITIONS.get(from_status, set())
    if to_status in allowed_targets:
        return
    allowed_str = ", ".join(sorted(status.value for status in allowed_targets)) or "none"
    raise HTTPException(
        status_code=400,
        detail=(
            f"Transition cash request invalide: {from_status.value} -> {to_status.value}. "
            f"Transitions autorisees depuis {from_status.value}: {allowed_str}."
        ),
    )


def transition_cash_request_status(
    request: WalletCashRequests,
    to_status: WalletCashRequestStatus,
) -> WalletCashRequestStatus:
    from_status = request.status
    validate_cash_request_transition(from_status, to_status)
    request.status = to_status
    return to_status

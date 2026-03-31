from app.models.external_transfers import ExternalTransfers


EXTERNAL_TRANSFER_STATUS_PENDING = "pending"
EXTERNAL_TRANSFER_STATUS_APPROVED = "approved"
EXTERNAL_TRANSFER_STATUS_COMPLETED = "completed"
EXTERNAL_TRANSFER_STATUS_SUCCEEDED = "succeeded"
EXTERNAL_TRANSFER_STATUS_FAILED = "failed"
EXTERNAL_TRANSFER_STATUS_CANCELLED = "cancelled"


EXTERNAL_TRANSFER_TO_TRANSACTION_STATUS: dict[str, str] = {
    EXTERNAL_TRANSFER_STATUS_PENDING: "pending",
    EXTERNAL_TRANSFER_STATUS_APPROVED: "initiated",
    EXTERNAL_TRANSFER_STATUS_COMPLETED: "completed",
    EXTERNAL_TRANSFER_STATUS_SUCCEEDED: "succeeded",
    EXTERNAL_TRANSFER_STATUS_FAILED: "failed",
    EXTERNAL_TRANSFER_STATUS_CANCELLED: "cancelled",
}


ALLOWED_EXTERNAL_TRANSFER_TRANSITIONS: dict[str, set[str]] = {
    EXTERNAL_TRANSFER_STATUS_PENDING: {
        EXTERNAL_TRANSFER_STATUS_APPROVED,
        EXTERNAL_TRANSFER_STATUS_FAILED,
        EXTERNAL_TRANSFER_STATUS_CANCELLED,
        EXTERNAL_TRANSFER_STATUS_SUCCEEDED,
        EXTERNAL_TRANSFER_STATUS_COMPLETED,
    },
    EXTERNAL_TRANSFER_STATUS_APPROVED: {
        EXTERNAL_TRANSFER_STATUS_COMPLETED,
        EXTERNAL_TRANSFER_STATUS_SUCCEEDED,
        EXTERNAL_TRANSFER_STATUS_FAILED,
        EXTERNAL_TRANSFER_STATUS_CANCELLED,
    },
    EXTERNAL_TRANSFER_STATUS_COMPLETED: set(),
    EXTERNAL_TRANSFER_STATUS_SUCCEEDED: set(),
    EXTERNAL_TRANSFER_STATUS_FAILED: set(),
    EXTERNAL_TRANSFER_STATUS_CANCELLED: set(),
}


def normalize_external_transfer_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    if value in {"success", EXTERNAL_TRANSFER_STATUS_SUCCEEDED}:
        return EXTERNAL_TRANSFER_STATUS_SUCCEEDED
    return value


def validate_external_transfer_transition(from_status: str | None, to_status: str | None) -> None:
    current = normalize_external_transfer_status(from_status)
    target = normalize_external_transfer_status(to_status)
    if not target:
        raise ValueError("Statut externe invalide: valeur vide.")
    if current == target:
        return
    allowed = ALLOWED_EXTERNAL_TRANSFER_TRANSITIONS.get(current, set())
    if target in allowed:
        return
    allowed_text = ", ".join(sorted(allowed)) or "none"
    raise ValueError(
        f"Transition transfert externe invalide: {current or 'unknown'} -> {target}. "
        f"Transitions autorisees depuis {current or 'unknown'}: {allowed_text}."
    )


def transition_external_transfer_status(transfer: ExternalTransfers, to_status: str) -> None:
    current = normalize_external_transfer_status(getattr(transfer, "status", None))
    target = normalize_external_transfer_status(to_status)
    validate_external_transfer_transition(current, target)
    transfer.status = target


def map_external_transfer_to_transaction_status(status: str | None) -> str:
    normalized = normalize_external_transfer_status(status)
    return EXTERNAL_TRANSFER_TO_TRANSACTION_STATUS.get(normalized, "pending")

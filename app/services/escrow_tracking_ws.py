from __future__ import annotations

from datetime import datetime

from app.core.ws_manager import manager
from app.services.eta_service import estimate_remaining_time

TRACKING_STEPS = [
    ("CREATED", "Ordre cree"),
    ("FUNDED", "Crypto recue"),
    ("SWAPPED", "Conversion effectuee"),
    ("PAYOUT_PENDING", "Paiement en cours"),
    ("PAID_OUT", "Paye"),
]
TRACKING_STEP_INDEX = {code: index for index, (code, _) in enumerate(TRACKING_STEPS)}
TERMINAL_ESCROW_STATUSES = {"PAID_OUT", "CANCELLED", "EXPIRED", "REFUNDED", "FAILED"}
PROGRESS_MAP = {
    "CREATED": 10,
    "FUNDED": 40,
    "SWAPPED": 60,
    "PAYOUT_PENDING": 80,
    "PAID_OUT": 100,
}
FLOW_FLAG_PREFIX = "FLOW:"
FLOW_CRYPTO_TO_FIAT = "CRYPTO_TO_FIAT"
FLOW_FIAT_TO_CRYPTO = "FIAT_TO_CRYPTO"


def _status_to_str(status_value) -> str:
    return status_value.value if hasattr(status_value, "value") else str(status_value)


def _extract_flow_type(order) -> str:
    for flag in list(getattr(order, "flags", []) or []):
        value = str(flag)
        if value.startswith(FLOW_FLAG_PREFIX):
            candidate = value.split(":", 1)[1].strip().upper()
            if candidate in {FLOW_CRYPTO_TO_FIAT, FLOW_FIAT_TO_CRYPTO}:
                return candidate
    return FLOW_CRYPTO_TO_FIAT


def build_tracking_steps(current_status: str, timestamps: dict[str, datetime | None]) -> list[dict]:
    current_index = TRACKING_STEP_INDEX.get(current_status)
    steps: list[dict] = []
    for code, label in TRACKING_STEPS:
        is_timestamped = timestamps.get(code) is not None
        completed = is_timestamped if current_index is None else TRACKING_STEP_INDEX[code] <= current_index or is_timestamped
        steps.append(
            {
                "code": code,
                "label": label,
                "completed": completed,
                "at": timestamps.get(code),
            }
        )
    return steps


async def build_tracking_payload(order) -> dict:
    status = _status_to_str(order.status)
    timestamps = {
        "CREATED": getattr(order, "created_at", None),
        "FUNDED": getattr(order, "funded_at", None),
        "SWAPPED": getattr(order, "swapped_at", None),
        "PAYOUT_PENDING": getattr(order, "payout_initiated_at", None),
        "PAID_OUT": getattr(order, "paid_out_at", None),
    }
    eta_seconds = await estimate_remaining_time(order)
    progress = PROGRESS_MAP.get(status, 0)
    return {
        "order_id": str(order.id),
        "current_status": status,
        "flow_type": _extract_flow_type(order),
        "is_terminal": status in TERMINAL_ESCROW_STATUSES,
        "progress": progress,
        "eta_seconds": eta_seconds,
        "steps": build_tracking_steps(status, timestamps),
    }


async def broadcast_tracking_update(order) -> None:
    payload = await build_tracking_payload(order)
    payload["event"] = "STATUS_UPDATE"
    payload["status"] = payload["current_status"]
    await manager.broadcast(str(order.id), payload)

import os
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logger import get_logger
from app.models.userdevices import UserDevices

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency
    httpx = None


logger = get_logger("push")

FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY")
FCM_ENDPOINT = os.getenv("FCM_ENDPOINT", "https://fcm.googleapis.com/fcm/send")
MAX_FCM_BATCH = 500


async def register_user_device(
    db: AsyncSession,
    *,
    user_id: UUID,
    push_token: str,
    device_fingerprint: Optional[str] = None,
) -> UserDevices:
    """
    Upsert a user device entry so we always keep the latest push token per device.
    """
    stmt = select(UserDevices).where(UserDevices.user_id == user_id)
    if device_fingerprint:
        stmt = stmt.where(UserDevices.device_fingerprint == device_fingerprint)
    else:
        stmt = stmt.where(UserDevices.push_token == push_token)

    device = await db.scalar(stmt)
    if device:
        device.push_token = push_token
        if device_fingerprint:
            device.device_fingerprint = device_fingerprint
    else:
        device = UserDevices(
            user_id=user_id,
            push_token=push_token,
            device_fingerprint=device_fingerprint,
        )
        db.add(device)

    await db.commit()
    await db.refresh(device)
    return device


async def list_user_devices(db: AsyncSession, *, user_id: UUID) -> Sequence[UserDevices]:
    stmt = (
        select(UserDevices)
        .where(UserDevices.user_id == user_id)
        .order_by(UserDevices.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def revoke_user_device(
    db: AsyncSession,
    *,
    user_id: UUID,
    device_id: UUID,
) -> bool:
    stmt = (
        delete(UserDevices)
        .where(UserDevices.user_id == user_id)
        .where(UserDevices.device_id == device_id)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


async def _get_tokens(db: AsyncSession, user_id: UUID) -> List[Dict[str, Any]]:
    stmt = select(UserDevices.device_id, UserDevices.push_token).where(
        UserDevices.user_id == user_id, UserDevices.push_token.is_not(None)
    )
    rows = await db.execute(stmt)
    return [
        {"device_id": str(device_id), "push_token": token}
        for device_id, token in rows.all()
        if token
    ]


async def send_push_notification(
    db: AsyncSession,
    *,
    user_id: UUID,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send a push notification via FCM to every device registered for the user.
    Returns True if at least one message was accepted by the provider.
    """
    tokens = await _get_tokens(db, user_id)
    if not tokens:
        logger.info("No push token registered for user %s", user_id)
        return False

    if not FCM_SERVER_KEY:
        logger.warning("FCM_SERVER_KEY is missing; skipping push send")
        return False

    if httpx is None:
        logger.warning("httpx is not installed; cannot call FCM endpoint")
        return False

    headers = {
        "Authorization": f"key={FCM_SERVER_KEY}",
        "Content-Type": "application/json",
    }

    invalid_devices: List[UUID] = []
    success = False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for i in range(0, len(tokens), MAX_FCM_BATCH):
                chunk = tokens[i : i + MAX_FCM_BATCH]
                payload = {
                    "registration_ids": [t["push_token"] for t in chunk],
                    "notification": {"title": title, "body": body},
                    "data": data or {},
                }
                resp = await client.post(FCM_ENDPOINT, headers=headers, json=payload)
                resp.raise_for_status()
                resp_json = resp.json()
                results = resp_json.get("results", [])
                if resp_json.get("success", 0):
                    success = True
                for idx, result in enumerate(results):
                    if "error" in result and result["error"] in {
                        "NotRegistered",
                        "InvalidRegistration",
                        "MismatchSenderId",
                    }:
                        invalid_devices.append(UUID(chunk[idx]["device_id"]))
    except Exception as exc:  # pragma: no cover - network failure
        logger.error("Push notification error: %s", exc)

    if invalid_devices:
        await db.execute(
            delete(UserDevices).where(UserDevices.device_id.in_(invalid_devices))
        )
        await db.commit()
        logger.info("Cleaned %s invalid push tokens", len(invalid_devices))

    return success

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import Users
from app.services.mailer import send_email
from app.services.push_notifications import (
    list_user_devices,
    register_user_device,
    revoke_user_device,
    send_push_notification,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class DeviceRegisterPayload(BaseModel):
    push_token: str
    device_fingerprint: str | None = None


class TestPushPayload(BaseModel):
    title: str
    body: str
    data: dict | None = None


@router.get("/test-email")
async def test_email():
    send_email(
        to="tonemail@gmail.com",
        subject="Test d'envoi PayLink",
        template_name="payment_confirmation.html",
        user_name="Adolphe",
        amount="250.00",
        currency="EUR",
        transaction_id="TXN-2025-001",
        date=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
    return {"message": "Email de test envoye avec succes"}


@router.post("/devices")
async def register_device(
    payload: DeviceRegisterPayload,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if not payload.push_token.strip():
        raise HTTPException(status_code=400, detail="push_token requis")

    device = await register_user_device(
        db,
        user_id=current_user.user_id,
        push_token=payload.push_token.strip(),
        device_fingerprint=payload.device_fingerprint,
    )

    return {
        "device_id": str(device.device_id),
        "user_id": str(device.user_id),
        "push_token": device.push_token,
        "device_fingerprint": device.device_fingerprint,
        "created_at": device.created_at,
    }


@router.get("/devices")
async def list_devices(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    devices = await list_user_devices(db, user_id=current_user.user_id)
    return [
        {
            "device_id": str(d.device_id),
            "push_token": d.push_token,
            "device_fingerprint": d.device_fingerprint,
            "created_at": d.created_at,
        }
        for d in devices
    ]


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: UUID = Path(..., description="Identifiant du device"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    deleted = await revoke_user_device(
        db, user_id=current_user.user_id, device_id=device_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Device introuvable")
    return {"status": "deleted", "device_id": str(device_id)}


@router.post("/push/test")
async def send_test_push(
    payload: TestPushPayload,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    sent = await send_push_notification(
        db,
        user_id=current_user.user_id,
        title=payload.title,
        body=payload.body,
        data=payload.data,
    )
    return {"sent": sent}

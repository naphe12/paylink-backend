from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.payment_events import PaymentEvents
from app.models.payment_intents import PaymentIntents
from app.models.users import Users
from app.schemas.payments import (
    PaymentEventRead,
    PaymentIntentAdminDetailRead,
    PaymentIntentAdminRead,
    PaymentIntentAdminStatusActionCreate,
    PaymentIntentManualReconcileCreate,
    PaymentIntentRead,
    PaymentIntentUserLiteRead,
)
from app.services.payments_service import admin_reconcile_payment_intent, admin_update_payment_intent_status


router = APIRouter(prefix="/admin/payments", tags=["Admin Payments"])


@router.get("/intents", response_model=list[PaymentIntentAdminRead])
async def list_admin_payment_intents(
    limit: int = Query(100, ge=1, le=500),
    status: str | None = Query(None),
    provider_code: str | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    stmt = (
        select(PaymentIntents, Users)
        .join(Users, Users.user_id == PaymentIntents.user_id)
        .order_by(desc(PaymentIntents.created_at))
        .limit(limit)
    )
    if status:
        stmt = stmt.where(PaymentIntents.status == str(status).strip())
    if provider_code:
        stmt = stmt.where(PaymentIntents.provider_code == str(provider_code).strip())
    if q:
        pattern = f"%{str(q).strip()}%"
        stmt = stmt.where(
            or_(
                PaymentIntents.merchant_reference.ilike(pattern),
                PaymentIntents.provider_reference.ilike(pattern),
                PaymentIntents.payer_identifier.ilike(pattern),
                Users.full_name.ilike(pattern),
                Users.email.ilike(pattern),
                cast(Users.phone_e164, String).ilike(pattern),
            )
        )

    rows = (await db.execute(stmt)).all()
    return [
        PaymentIntentAdminRead(
            **PaymentIntentRead.model_validate(intent).model_dump(),
            user=PaymentIntentUserLiteRead(
                user_id=user.user_id,
                full_name=user.full_name,
                email=user.email,
                phone_e164=user.phone_e164,
            ),
        )
        for intent, user in rows
    ]


@router.get("/intents/{intent_id}", response_model=PaymentIntentAdminDetailRead)
async def get_admin_payment_intent_detail(
    intent_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    row = (
        await db.execute(
            select(PaymentIntents, Users)
            .join(Users, Users.user_id == PaymentIntents.user_id)
            .where(PaymentIntents.intent_id == intent_id)
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Intent de paiement introuvable.")

    intent, user = row
    events = (
        await db.execute(
            select(PaymentEvents)
            .where(PaymentEvents.intent_id == intent.intent_id)
            .order_by(desc(PaymentEvents.created_at))
        )
    ).scalars().all()

    return PaymentIntentAdminDetailRead(
        intent=PaymentIntentAdminRead(
            **PaymentIntentRead.model_validate(intent).model_dump(),
            user=PaymentIntentUserLiteRead(
                user_id=user.user_id,
                full_name=user.full_name,
                email=user.email,
                phone_e164=user.phone_e164,
            ),
        ),
        events=[PaymentEventRead.model_validate(item) for item in events],
    )


@router.post("/intents/{intent_id}/manual-reconcile", response_model=PaymentIntentAdminDetailRead)
async def manual_reconcile_admin_payment_intent(
    intent_id: UUID,
    payload: PaymentIntentManualReconcileCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: Users = Depends(get_current_admin),
):
    await admin_reconcile_payment_intent(
        db,
        intent_id=intent_id,
        admin_user_id=current_admin.user_id,
        provider_reference=payload.provider_reference,
        note=payload.note,
    )
    return await get_admin_payment_intent_detail(intent_id, db, current_admin)


@router.post("/intents/{intent_id}/status-action", response_model=PaymentIntentAdminDetailRead)
async def status_action_admin_payment_intent(
    intent_id: UUID,
    payload: PaymentIntentAdminStatusActionCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: Users = Depends(get_current_admin),
):
    await admin_update_payment_intent_status(
        db,
        intent_id=intent_id,
        admin_user_id=current_admin.user_id,
        action=payload.action,
        note=payload.note,
    )
    return await get_admin_payment_intent_detail(intent_id, db, current_admin)

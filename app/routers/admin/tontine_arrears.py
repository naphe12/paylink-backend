from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Text, cast, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.notifications import Notifications
from app.models.tontinecontributions import TontineContributions, ContributionStatus
from app.models.tontines import Tontines
from app.models.users import Users

router = APIRouter(prefix="/admin/tontines", tags=["Admin Tontines"])

OVERDUE_GRACE_DAYS = 3


def _as_datetime(value: datetime | date | time | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, time):
        return datetime.combine(datetime.utcnow().date(), value, tzinfo=timezone.utc)
    return datetime.utcnow().astimezone(timezone.utc)


@router.get("/arrears")
async def list_overdue_contributions(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    now = datetime.utcnow().astimezone(timezone.utc)
    stmt = (
        select(
            TontineContributions,
            Users.full_name.label("member_name"),
            Users.email,
            Users.phone_e164,
            Tontines.name.label("tontine_name"),
            Tontines.periodicity_days,
            Tontines.status.label("tontine_status"),
        )
        .join(Users, Users.user_id == TontineContributions.user_id)
        .join(Tontines, Tontines.tontine_id == TontineContributions.tontine_id)
        .where(cast(TontineContributions.status, Text) != ContributionStatus.paid.value)
    )

    rows = await db.execute(stmt)

    overdue_entries = []
    for contrib, member_name, email, phone, tontine_name, periodicity_days, tontine_status in rows.all():
        created_at = _as_datetime(contrib.created_at)
        due_date = created_at + timedelta(days=periodicity_days or OVERDUE_GRACE_DAYS)
        if due_date + timedelta(days=OVERDUE_GRACE_DAYS) < now:


            overdue_entries.append(
                {
                    "contribution_id": str(contrib.contribution_id),
                    "tontine_id": str(contrib.tontine_id),
                    "tontine_name": tontine_name,
                    "member_name": member_name,
                    "email": email,
                    "phone": phone,
                    "amount": float(contrib.amount),
                    "status": contrib.status.value if isinstance(contrib.status, ContributionStatus) else contrib.status,
                    "created_at": created_at.isoformat(),
                    "due_date": due_date.isoformat(),
                    "tontine_status": tontine_status,
                }
            )

    return overdue_entries


@router.post("/arrears/notify/{tontine_id}")
async def notify_overdue_members(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    overdue_stmt = (
        select(TontineContributions, Users.full_name, Users.user_id)
        .join(Users, Users.user_id == TontineContributions.user_id)
        .where(
            TontineContributions.tontine_id == tontine_id,
            cast(TontineContributions.status, Text) != ContributionStatus.paid.value,
        )
    )

    rows = await db.execute(overdue_stmt)
    notifications = []
    for contrib, full_name, user_id in rows.all():
        notifications.append(
            Notifications(
                user_id=user_id,
                channel="in_app",
                subject="Contribution en retard",
                message=f"Bonjour {full_name}, votre contribution de {contrib.amount} BIF est en retard.",
            )
        )
    if notifications:
        db.add_all(notifications)
        await db.commit()
    return {"notified": len(notifications)}


@router.post("/arrears/block/{tontine_id}")
async def block_tontine(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    tontine.status = "paused"
    tontine.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Tontine mise en pause"}

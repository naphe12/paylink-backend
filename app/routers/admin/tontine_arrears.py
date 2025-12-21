from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Text, cast, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.notifications import Notifications
from app.models.tontinecontributions import TontineContributions, ContributionStatus
from app.models.tontinemembers import TontineMembers
from app.models.tontines import Tontines
from app.models.users import Users
from pydantic import BaseModel, Field

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


class AdminTontineCreate(BaseModel):
    owner_user: UUID = Field(..., description="User ID du créateur")
    name: str
    currency_code: str = Field(..., min_length=3, max_length=3)
    periodicity_days: int = Field(30, ge=1)
    amount_per_member: Decimal = Field(..., gt=0)
    tontine_type: str = Field(..., pattern="^(rotative|epargne)$")
    member_ids: List[UUID] = Field(default_factory=list, description="Liste des membres à ajouter")


@router.post("", status_code=201)
async def create_tontine_admin(
    payload: AdminTontineCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    # Vérifier owner
    owner = await db.scalar(select(Users).where(Users.user_id == payload.owner_user))
    if not owner:
        raise HTTPException(404, "Owner introuvable")

    allowed_types = {"rotative", "epargne"}
    if payload.tontine_type not in allowed_types:
        raise HTTPException(400, "tontine_type invalide (rotative|epargne)")

    now = datetime.utcnow().astimezone(timezone.utc)
    tontine = Tontines(
        owner_user=payload.owner_user,
        name=payload.name,
        currency_code=payload.currency_code.upper(),
        periodicity_days=payload.periodicity_days,
        status="active",
        current_round=0,
        next_rotation_at=now + timedelta(days=payload.periodicity_days),
        tontine_type=payload.tontine_type,
        common_pot=Decimal("0"),
        last_rotation_at=now,
        amount_per_member=payload.amount_per_member,
    )
    db.add(tontine)
    await db.flush()  # obtient tontine_id

    # Ajouter membres (optionnel)
    member_ids_unique = list(dict.fromkeys(payload.member_ids))  # garder l'ordre, retirer doublons
    if member_ids_unique:
        users_rows = (
            await db.execute(
                select(Users.user_id, Users.full_name, Users.email).where(
                    Users.user_id.in_(member_ids_unique)
                )
            )
        ).all()
        found_map = {row.user_id: (row.full_name, row.email) for row in users_rows}

        members_to_add = []
        for idx, member_id in enumerate(member_ids_unique):
            names = found_map.get(member_id)
            if not names:
                raise HTTPException(404, f"Membre introuvable: {member_id}")
            full_name, email = names
            members_to_add.append(
                TontineMembers(
                    tontine_id=tontine.tontine_id,
                    user_id=member_id,
                    join_order=idx,
                    user_name=full_name or email or "Membre",
                )
            )
        db.add_all(members_to_add)

    await db.commit()
    await db.refresh(tontine)

    return {
        "tontine_id": str(tontine.tontine_id),
        "owner_user": str(tontine.owner_user),
        "name": tontine.name,
        "currency_code": tontine.currency_code,
        "periodicity_days": tontine.periodicity_days,
        "status": tontine.status,
        "tontine_type": tontine.tontine_type,
        "amount_per_member": float(tontine.amount_per_member),
        "members_added": len(payload.member_ids),
    }

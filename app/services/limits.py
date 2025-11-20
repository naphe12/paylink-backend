# app/services/limits.py
from datetime import date
from sqlalchemy import select, update, insert, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.limitusage import LimitUsage
from app.models.users import Users
from fastapi import HTTPException

async def guard_and_increment_limits(
    db: AsyncSession, user: Users, amount: float
):
    # Récupère ligne du mois/jour en cours, sinon crée
    today = date.today()
    first_of_month = today.replace(day=1)

    row = await db.scalar(
        select(LimitUsage).where(
            LimitUsage.user_id == user.user_id,
            LimitUsage.day == today,
            LimitUsage.month == first_of_month
        )
    )
    if not row:
        await db.execute(insert(LimitUsage).values(
            user_id=user.user_id, day=today, month=first_of_month,
            used_daily=0, used_monthly=0
        ))

    # Recalcule usage courant (lecture fraiche)
    usage = await db.execute(
        select(LimitUsage.used_daily, LimitUsage.used_monthly)
        .where(
            LimitUsage.user_id == user.user_id,
            LimitUsage.day == today,
            LimitUsage.month == first_of_month
        )
        .with_for_update()
    )
    used_daily, used_monthly = usage.first() or (0, 0)

    # Vérifs
    new_daily = float(used_daily) + amount
    new_monthly = float(used_monthly) + amount
    if new_daily > float(user.daily_limit):
        raise HTTPException(429, "Limite journalière dépassée")
    if new_monthly > float(user.monthly_limit):
        raise HTTPException(429, "Limite mensuelle dépassée")

    # Incrémente
    await db.execute(
        update(LimitUsage)
        .where(
            LimitUsage.user_id == user.user_id,
            LimitUsage.day == today,
            LimitUsage.month == first_of_month
        )
        .values(
            used_daily=text("used_daily + :inc"),
            used_monthly=text("used_monthly + :inc"),
        )
        .execution_options(synchronize_session=False),
        {"inc": amount}
    )

from datetime import date
from sqlalchemy import update
from app.models.users import Users

async def reset_limits_if_needed(db, user: Users):
    today = date.today()

    # Si on change de jour → reset daily
    if user.last_reset != today:
        user.used_daily = 0
        user.used_monthly = 0
        user.last_reset = today
        await db.commit()

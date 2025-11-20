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

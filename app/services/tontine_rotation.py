from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tontinemembers import TontineMembers
from app.models.tontines import Tontines


async def process_tontine_rotations(db: AsyncSession):
    now = datetime.utcnow()

    tontines = (await db.scalars(
        select(Tontines).where(
            Tontines.tontine_type == "rotative",
            Tontines.next_rotation_at <= now
        )
    )).all()

    for tontine in tontines:
        members = (await db.scalars(
            select(TontineMembers)
            .where(TontineMembers.tontine_id == tontine.id)
            .order_by(TontineMembers.join_order)
        )).all()

        if not members:
            continue

        tontine.current_round = (tontine.current_round + 1) % len(members)
        tontine.next_rotation_at = now + timedelta(days=7)  # Rotation tous les 7 jours

    await db.commit()

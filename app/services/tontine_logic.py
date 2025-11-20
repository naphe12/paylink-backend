from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.tontinecontributions import TontineContributions
from app.models.tontinemembers import TontineMembers
from app.models.tontines import Tontines
from app.websocket_manager import ws_push_room


async def apply_contribution_effect(tontine_id: str, user_id: str, amount: float, db):
    # ✅ Charger la tontine
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        return

    # ✅ Type épargne → augmenter pot commun
    if tontine.tontine_type == "epargne":
        tontine.common_pot = (tontine.common_pot or 0) + amount
        await db.commit()

        # 🔔 Notifier les membres (websocket)
        await ws_push_room(str(tontine_id), {
            "type": "common_pot_update",
            "pot": float(tontine.common_pot)
        })
        return

    # ✅ Type rotative → vérifier si tout le monde a payé
    members = await db.scalars(select(TontineMembers).where(TontineMembers.tontine_id == tontine_id))
    members = members.all()

    contributions = await db.scalars(
        select(TontineContributions.user_id)
        .where(TontineContributions.tontine_id == tontine_id)
        .where(TontineContributions.paid_at >= tontine.current_round_start)
    )
    paid_users = set(contributions.all())

    all_paid = all(m.user_id in paid_users for m in members)

    if all_paid:
        # 🎯 Passer au prochain tour
        tontine.current_round = (tontine.current_round + 1) % len(members)
        tontine.current_round_start = datetime.utcnow()
        tontine.next_rotation_at = datetime.utcnow() + timedelta(days=tontine.rotation_interval_days)

        await db.commit()

        # 🔔 Broadcast WebSocket
        await ws_push_room(str(tontine_id), {
            "type": "rotation_changed",
            "current_round": tontine.current_round,
            "next_rotation_at": tontine.next_rotation_at.isoformat()
        })

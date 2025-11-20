from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user  # ✅ important
from app.models.tontinecontributions import TontineContributions
from app.models.tontines import Tontines
from app.websocket_manager import ws_push_room

router = APIRouter()

@router.post("/tontines/{tontine_id}/contribute/wallet")
async def contribute_wallet(tontine_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    # 1) Vérifier que la tontine existe
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(status_code=404, detail="Tontine introuvable")

    # 2) Créer la contribution (simple pour l'exemple)
    contrib = TontineContributions(
        tontine_id=tontine_id,
        user_id=current_user.user_id,
        amount=tontine.amount_per_member,
        status="paid"
    )
    db.add(contrib)
    await db.commit()

    # ✅ 3) Push WebSocket à la Room Tontine
    await ws_push_room(str(tontine_id), {
        "type": "contribution_update",
        "data": {
            "tontine_id": str(tontine_id),
            "user_id": str(current_user.user_id),
            "amount": float(tontine.amount_per_member),
            "status": "paid"
        }
    })

    return {"message": "Contribution enregistrée ✅"}



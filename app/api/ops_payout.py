from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.payout_orchestrator import assign_agent_and_notify

router = APIRouter()


class InitiatePayoutRequest(BaseModel):
    order_id: str
    amount_bif: float


@router.post("/ops/payouts/initiate")
async def initiate_payout(payload: InitiatePayoutRequest):
    try:
        res = await assign_agent_and_notify(payload.order_id, payload.amount_bif)
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

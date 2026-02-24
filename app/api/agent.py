from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import async_session_maker
from app.services.paylink_ledger_service import PaylinkLedgerService

router = APIRouter()


def _jsonable(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@router.get("/agent/assignments")
async def list_assignments(agent_id: str):
    async with async_session_maker() as db:
        res = await db.execute(
            text(
                """
                SELECT a.id, a.order_id, a.amount_bif, a.status, a.assigned_at
                FROM paylink.assignments a
                WHERE a.agent_id = CAST(:aid AS uuid)
                ORDER BY a.assigned_at DESC
                LIMIT 100
                """
            ),
            {"aid": agent_id},
        )
        items = []
        for row in res.mappings().all():
            items.append({k: _jsonable(v) for k, v in row.items()})
        return {"items": items}


class ConfirmRequest(BaseModel):
    agent_id: str
    lumicash_ref: str | None = None
    note: str | None = None


@router.post("/agent/assignments/{assignment_id}/confirm")
async def confirm_assignment(assignment_id: str, payload: ConfirmRequest):
    async with async_session_maker() as db:
        row = await db.execute(
            text(
                """
                SELECT id, order_id, amount_bif, status
                FROM paylink.assignments
                WHERE id = CAST(:id AS uuid) AND agent_id = CAST(:aid AS uuid)
                """
            ),
            {"id": assignment_id, "aid": payload.agent_id},
        )
        assignment = row.mappings().first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        if assignment["status"] != "ASSIGNED":
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {assignment['status']}",
            )

        await db.execute(
            text(
                """
                UPDATE paylink.assignments
                SET status = 'CONFIRMED',
                    confirmed_at = now(),
                    note = COALESCE(:note, '')
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {
                "id": assignment_id,
                "note": payload.note or payload.lumicash_ref or "",
            },
        )

        # finalize ledger: reserved -> out
        await PaylinkLedgerService.post_journal(
            db,
            tx_id=uuid4(),
            description="Payout executed by agent",
            postings=[
                {
                    "account_code": "PAYOUT_RESERVED_BIF",
                    "direction": "DEBIT",
                    "amount": Decimal(str(assignment["amount_bif"])),
                    "currency": "BIF",
                },
                {
                    "account_code": "PAYOUTS_BIF_OUT",
                    "direction": "CREDIT",
                    "amount": Decimal(str(assignment["amount_bif"])),
                    "currency": "BIF",
                },
            ],
            metadata={
                "event": "AGENT_PAYOUT_CONFIRMED",
                "assignment_id": assignment_id,
                "agent_id": payload.agent_id,
                "order_id": str(assignment["order_id"]),
            },
        )

        # update escrow order status
        await db.execute(
            text(
                """
                UPDATE escrow.orders
                SET status = 'PAID_OUT',
                    paid_out_at = now(),
                    updated_at = now()
                WHERE id = CAST(:oid AS uuid)
                """
            ),
            {"oid": str(assignment["order_id"])},
        )

        await db.commit()

    return {"ok": True}

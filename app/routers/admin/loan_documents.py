import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.loans import Loans

router = APIRouter(prefix="/admin/loans", tags=["Admin Loans"])


@router.get("/{loan_id}/documents")
async def get_loan_documents(
    loan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    loan = await db.get(Loans, loan_id)
    if not loan:
        raise HTTPException(404, "Pret introuvable.")
    return loan.metadata_ or {}


@router.post("/{loan_id}/documents/validate")
async def validate_loan_documents(
    loan_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    loan = await db.get(Loans, loan_id)
    if not loan:
        raise HTTPException(404, "Pret introuvable.")

    status = (payload.get("status") or "").lower()
    if status not in {"approved", "rejected"}:
        raise HTTPException(400, "Status documents invalide (approved/rejected).")

    meta = loan.metadata_ or {}
    meta["documents_status"] = status
    if payload.get("note"):
        meta["documents_note"] = payload.get("note")
    loan.metadata_ = meta
    await db.commit()
    return {"documents_status": status, "loan_id": str(loan.loan_id)}

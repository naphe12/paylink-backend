import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin

router = APIRouter(prefix="/admin/loans", tags=["Admin Loans"])


def _row_to_collateral(row) -> dict:
    return {
        "collateral_id": str(row["collateral_id"]),
        "loan_id": str(row["loan_id"]),
        "type": row["type"],
        "value_estimated": float(row["value_estimated"]) if row["value_estimated"] is not None else None,
        "details": row["details"],
        "created_at": row["created_at"],
    }


@router.get("/{loan_id}/collaterals")
async def list_collaterals(
    loan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    rows = (
        await db.execute(
            text("SELECT * FROM paylink.collaterals WHERE loan_id = :loan_id ORDER BY created_at DESC"),
            {"loan_id": str(loan_id)},
        )
    ).mappings().all()
    return [_row_to_collateral(r) for r in rows]


@router.post("/{loan_id}/collaterals")
async def add_collateral(
    loan_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    ctype = payload.get("type")
    if not ctype:
        raise HTTPException(400, "Type de collaterale requis.")
    value_estimated = payload.get("value_estimated")
    details = payload.get("details")
    sql = """
        INSERT INTO paylink.collaterals (loan_id, type, value_estimated, details)
        VALUES (:loan_id, :ctype, :value_estimated, :details)
        RETURNING *
    """
    row = (
        await db.execute(
            text(sql),
            {
                "loan_id": str(loan_id),
                "ctype": ctype,
                "value_estimated": Decimal(value_estimated) if value_estimated is not None else None,
                "details": details,
            },
        )
    ).mappings().first()
    await db.commit()
    return _row_to_collateral(row)


@router.delete("/{loan_id}/collaterals/{collateral_id}")
async def delete_collateral(
    loan_id: uuid.UUID,
    collateral_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    res = await db.execute(
        text(
            "DELETE FROM paylink.collaterals WHERE loan_id = :loan_id AND collateral_id = :collateral_id"
        ),
        {"loan_id": str(loan_id), "collateral_id": str(collateral_id)},
    )
    if res.rowcount == 0:
        raise HTTPException(404, "Collaterale introuvable.")
    await db.commit()
    return {"message": "Collaterale supprimee"}

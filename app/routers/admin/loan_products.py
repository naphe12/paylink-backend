import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin

router = APIRouter(prefix="/admin/loan-products", tags=["Admin Loans"])


class LoanProductBase(BaseModel):
    name: str
    product_type: str = "consumer"  # consumer | business
    min_principal: Decimal
    max_principal: Decimal
    term_min_months: int
    term_max_months: int
    apr_percent: Decimal
    fee_flat: Decimal | None = None
    fee_percent: Decimal | None = None
    penalty_rate_percent: Decimal | None = None
    grace_days: int = 0
    require_documents: bool = False
    metadata: dict | None = None


class LoanProductCreate(LoanProductBase):
    pass


class LoanProductUpdate(BaseModel):
    name: str | None = None
    product_type: str | None = None
    min_principal: Decimal | None = None
    max_principal: Decimal | None = None
    term_min_months: int | None = None
    term_max_months: int | None = None
    apr_percent: Decimal | None = None
    fee_flat: Decimal | None = None
    fee_percent: Decimal | None = None
    penalty_rate_percent: Decimal | None = None
    grace_days: int | None = None
    require_documents: bool | None = None
    metadata: dict | None = None


def _row_to_product(row) -> dict:
    return {
        "product_id": str(row["product_id"]),
        "name": row["name"],
        "product_type": row["product_type"],
        "min_principal": float(row["min_principal"]),
        "max_principal": float(row["max_principal"]),
        "term_min_months": row["term_min_months"],
        "term_max_months": row["term_max_months"],
        "apr_percent": float(row["apr_percent"]),
        "fee_flat": float(row["fee_flat"]) if row["fee_flat"] is not None else None,
        "fee_percent": float(row["fee_percent"]) if row["fee_percent"] is not None else None,
        "penalty_rate_percent": float(row["penalty_rate_percent"]) if row["penalty_rate_percent"] is not None else None,
        "grace_days": row["grace_days"],
        "require_documents": bool(row["require_documents"]),
        "metadata": row["metadata"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
async def list_products(
    product_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    params = {}
    sql = "SELECT * FROM paylink.loan_products"
    if product_type:
        sql += " WHERE product_type = :product_type"
        params["product_type"] = product_type
    sql += " ORDER BY created_at DESC"
    rows = (await db.execute(text(sql), params)).mappings().all()
    return [_row_to_product(r) for r in rows]


@router.post("")
async def create_product(
    payload: LoanProductCreate,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    sql = """
    INSERT INTO paylink.loan_products
    (name, product_type, min_principal, max_principal, term_min_months, term_max_months,
     apr_percent, fee_flat, fee_percent, penalty_rate_percent, grace_days, require_documents, metadata)
    VALUES (:name, :product_type, :min_principal, :max_principal, :term_min_months, :term_max_months,
            :apr_percent, :fee_flat, :fee_percent, :penalty_rate_percent, :grace_days, :require_documents, :metadata)
    RETURNING *
    """
    row = (
        await db.execute(
            text(sql),
            {
                "name": payload.name,
                "product_type": payload.product_type,
                "min_principal": payload.min_principal,
                "max_principal": payload.max_principal,
                "term_min_months": payload.term_min_months,
                "term_max_months": payload.term_max_months,
                "apr_percent": payload.apr_percent,
                "fee_flat": payload.fee_flat,
                "fee_percent": payload.fee_percent,
                "penalty_rate_percent": payload.penalty_rate_percent,
                "grace_days": payload.grace_days,
                "require_documents": payload.require_documents,
                "metadata": payload.metadata,
            },
        )
    ).mappings().first()
    await db.commit()
    return _row_to_product(row)


@router.patch("/{product_id}")
async def update_product(
    product_id: uuid.UUID,
    payload: LoanProductUpdate,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(400, "Aucune donnée à mettre à jour")

    set_parts = [f"{col} = :{col}" for col in data.keys()]
    data["product_id"] = str(product_id)
    sql = f"UPDATE paylink.loan_products SET {', '.join(set_parts)}, updated_at = now() WHERE product_id = :product_id RETURNING *"
    row = (await db.execute(text(sql), data)).mappings().first()
    if not row:
        raise HTTPException(404, "Produit introuvable")
    await db.commit()
    return _row_to_product(row)


@router.delete("/{product_id}")
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin),
):
    res = await db.execute(text("DELETE FROM paylink.loan_products WHERE product_id = :pid"), {"pid": str(product_id)})
    if res.rowcount == 0:
        raise HTTPException(404, "Produit introuvable")
    await db.commit()
    return {"message": "Produit supprimé"}

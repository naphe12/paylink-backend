import csv
from io import StringIO
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users

router = APIRouter(prefix="/backoffice/escrow/audit", tags=["Backoffice - Audit Export"])

def _require_audit_role(user: Users) -> None:
    if str(getattr(user, "role", "")).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Acces reserve admin/operator")


@router.get("/export.csv")
async def export_csv(
    status: str | None = None,
    min_risk: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_audit_role(user)
    status_filter = None if str(status or "").upper() in {"", "ALL"} else str(status).upper()
    q = """
      SELECT
        o.id,
        o.status::text,
        o.user_id,
        u.full_name AS user_name,
        o.trader_id,
        t.full_name AS trader_name,
        o.usdc_expected,
        o.usdc_received,
        o.usdt_target,
        o.usdt_received,
        o.bif_target,
        o.bif_paid,
        o.risk_score,
        o.deposit_network,
        o.deposit_address,
        o.deposit_tx_hash,
        o.payout_provider,
        o.payout_reference,
        o.funded_at,
        o.swapped_at,
        o.payout_initiated_at,
        o.paid_out_at,
        o.created_at,
        o.updated_at
      FROM escrow.orders o
      LEFT JOIN paylink.users u ON u.user_id = o.user_id
      LEFT JOIN paylink.users t ON t.user_id = o.trader_id
      WHERE (:status IS NULL OR o.status::text = :status)
        AND (:min_risk IS NULL OR COALESCE(o.risk_score, 0) >= :min_risk)
        AND (:created_from IS NULL OR o.created_at >= :created_from)
        AND (:created_to IS NULL OR o.created_at <= :created_to)
      ORDER BY created_at DESC
      LIMIT 5000
    """
    res = await db.execute(
        text(q),
        {
            "status": status_filter,
            "min_risk": min_risk,
            "created_from": created_from,
            "created_to": created_to,
        },
    )
    rows = res.fetchall()

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "status",
            "user_id",
            "user_name",
            "trader_id",
            "trader_name",
            "usdc_expected",
            "usdc_received",
            "usdt_target",
            "usdt_received",
            "bif_target",
            "bif_paid",
            "risk_score",
            "deposit_network",
            "deposit_address",
            "deposit_tx_hash",
            "payout_provider",
            "payout_reference",
            "funded_at",
            "swapped_at",
            "payout_initiated_at",
            "paid_out_at",
            "created_at",
            "updated_at",
        ]
    )
    for r in rows:
        w.writerow(list(r))

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=escrow_audit.csv"},
    )

import csv
from io import StringIO
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
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    _require_audit_role(user)
    q = """
      SELECT id, status, usdc_expected, usdc_received, usdt_received, bif_target, bif_paid, created_at, updated_at
      FROM escrow.orders
      WHERE (:status IS NULL OR status = :status)
      ORDER BY created_at DESC
      LIMIT 5000
    """
    res = await db.execute(text(q), {"status": status})
    rows = res.fetchall()

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id","status","usdc_expected","usdc_received","usdt_received","bif_target","bif_paid","created_at","updated_at"])
    for r in rows:
        w.writerow(list(r))

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=escrow_audit.csv"},
    )

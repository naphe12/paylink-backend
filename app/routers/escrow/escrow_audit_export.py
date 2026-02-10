import csv
from io import StringIO
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/backoffice/escrow/audit", tags=["Backoffice - Audit Export"])

@router.get("/export.csv")
async def export_csv(status: str | None = None, db: AsyncSession = Depends(get_db)):
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

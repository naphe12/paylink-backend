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
from app.services.escrow_backoffice_read_service import fetch_escrow_order_rows
from app.services.escrow_backoffice_projection import (
    ESCROW_AUDIT_CSV_HEADERS,
    serialize_escrow_order_csv_row,
)

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
    res = await fetch_escrow_order_rows(
        db,
        status=status_filter,
        min_risk=min_risk,
        created_from=created_from,
        created_to=created_to,
        limit=5000,
    )
    rows = res.fetchall()

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(ESCROW_AUDIT_CSV_HEADERS)
    for r in rows:
        w.writerow(serialize_escrow_order_csv_row(r))

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=escrow_audit.csv"},
    )

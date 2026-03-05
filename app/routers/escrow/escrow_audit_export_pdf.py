from io import BytesIO
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


@router.get("/export.pdf")
async def export_pdf(
    status: str | None = None,
    min_risk: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    user: Users = Depends(get_current_user_db),
):
    try:
        from fpdf import FPDF
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF export indisponible: dependance fpdf2 manquante",
        ) from exc

    _require_audit_role(user)
    status_filter = None if str(status or "").upper() in {"", "ALL"} else str(status).upper()
    q = """
      SELECT
        o.id,
        o.status::text,
        COALESCE(u.full_name, CAST(o.user_id AS text)) AS user_label,
        o.usdc_expected,
        o.usdt_received,
        o.bif_target,
        COALESCE(o.risk_score, 0) AS risk_score,
        o.payout_reference,
        o.deposit_tx_hash,
        o.created_at
      FROM escrow.orders o
      LEFT JOIN paylink.users u ON u.user_id = o.user_id
      WHERE (:status IS NULL OR o.status::text = :status)
        AND (:min_risk IS NULL OR COALESCE(o.risk_score, 0) >= :min_risk)
        AND (:created_from IS NULL OR o.created_at >= :created_from)
        AND (:created_to IS NULL OR o.created_at <= :created_to)
      ORDER BY created_at DESC
      LIMIT 200
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

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "PayLink Escrow Audit Report", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Filter status: {status_filter or 'ALL'}", ln=1)
    pdf.cell(0, 7, f"Filter min_risk: {min_risk if min_risk is not None else 'N/A'}", ln=1)
    pdf.ln(2)
    pdf.set_font("Courier", "", 8)

    for r in rows:
        line = (
            f"{r[0]} | {r[1]} | user={r[2]} | USDC {r[3]} | USDT {r[4]} | "
            f"BIF {r[5]} | risk={r[6]} | ref={r[7] or '-'} | tx={r[8] or '-'} | {str(r[9])}"
        )
        pdf.multi_cell(0, 5, line[:180])

    data = pdf.output(dest="S")
    bio = BytesIO(data if isinstance(data, (bytes, bytearray)) else data.encode("latin-1"))
    bio.seek(0)

    return StreamingResponse(
        bio,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=escrow_audit.pdf"},
    )

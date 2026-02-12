from io import BytesIO
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
    q = """
      SELECT id, status, usdc_expected, usdt_received, bif_target, created_at
      FROM escrow.orders
      WHERE (:status IS NULL OR status = :status)
      ORDER BY created_at DESC
      LIMIT 200
    """
    res = await db.execute(text(q), {"status": status})
    rows = res.fetchall()

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "PayLink Escrow Audit Report", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Filter status: {status or 'ALL'}", ln=1)
    pdf.ln(2)
    pdf.set_font("Courier", "", 8)

    for r in rows:
        line = f"{r[0]} | {r[1]} | USDC {r[2]} | USDT {r[3]} | BIF {r[4]} | {str(r[5])}"
        pdf.multi_cell(0, 5, line[:180])

    data = pdf.output(dest="S")
    bio = BytesIO(data if isinstance(data, (bytes, bytearray)) else data.encode("latin-1"))
    bio.seek(0)

    return StreamingResponse(
        bio,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=escrow_audit.pdf"},
    )

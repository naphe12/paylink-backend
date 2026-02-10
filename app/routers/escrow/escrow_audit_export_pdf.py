from io import BytesIO
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from app.core.database import get_db

router = APIRouter(prefix="/backoffice/escrow/audit", tags=["Backoffice - Audit Export"])

@router.get("/export.pdf")
async def export_pdf(status: str | None = None, db: AsyncSession = Depends(get_db)):
    q = """
      SELECT id, status, usdc_expected, usdt_received, bif_target, created_at
      FROM escrow.orders
      WHERE (:status IS NULL OR status = :status)
      ORDER BY created_at DESC
      LIMIT 200
    """
    res = await db.execute(text(q), {"status": status})
    rows = res.fetchall()

    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4

    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "PayLink Escrow Audit Report")
    y -= 24

    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Filter status: {status or 'ALL'}")
    y -= 18

    c.setFont("Helvetica", 8)
    for r in rows:
        line = f"{r[0]} | {r[1]} | USDC {r[2]} | USDT {r[3]} | BIF {r[4]} | {str(r[5])}"
        c.drawString(40, y, line[:140])
        y -= 12
        if y < 60:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 8)

    c.showPage()
    c.save()
    bio.seek(0)

    return StreamingResponse(
        bio,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=escrow_audit.pdf"},
    )

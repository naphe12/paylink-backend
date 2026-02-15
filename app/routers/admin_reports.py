import io

from fastapi import APIRouter, Depends, Response
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.aml_case import AMLCase
from app.models.users import Users

router = APIRouter(prefix="/admin/reports", tags=["Admin Reports"])


@router.get("/aml-cases.pdf")
async def aml_cases_pdf(
    status: str = "OPEN",
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    cases = (
        (
            await db.execute(
                select(AMLCase)
                .where(AMLCase.status == status)
                .order_by(AMLCase.created_at.desc())
                .limit(500)
            )
        )
        .scalars()
        .all()
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"AML Cases Report (status={status})")
    y -= 24

    c.setFont("Helvetica", 10)
    for cs in cases:
        line = (
            f"{cs.created_at} | case={cs.case_id} | user={cs.user_id} | "
            f"trade={cs.trade_id} | score={cs.risk_score}"
        )
        c.drawString(40, y, line[:120])
        y -= 14
        if y < 60:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 10)

    c.showPage()
    c.save()
    pdf = buf.getvalue()

    return Response(content=pdf, media_type="application/pdf")

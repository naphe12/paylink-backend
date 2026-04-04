from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from textwrap import wrap
from typing import Any

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_accounts import AgentAccounts
from app.models.agents import Agents
from app.models.users import Users

EURO_ZONE_COUNTRY_CODES = {
    "AT",
    "BE",
    "CY",
    "DE",
    "EE",
    "ES",
    "FI",
    "FR",
    "GR",
    "HR",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PT",
    "SI",
    "SK",
}

_BG_COLOR = (245, 247, 251)
_CARD_COLOR = (255, 255, 255)
_HEADER_COLOR = (11, 59, 100)
_TEXT_COLOR = (31, 41, 55)
_MUTED_COLOR = (75, 85, 99)
_ACCENT_COLOR = (17, 94, 155)
_BORDER_COLOR = (222, 226, 234)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _quantize_amount(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_note_amount(value: Decimal | str | int | float, currency: str) -> str:
    amount = _quantize_amount(value)
    rendered = f"{amount:,.2f}".replace(",", " ")
    return f"{rendered} {str(currency or '').upper()}".strip()


async def resolve_payment_instruction(
    db: AsyncSession,
    *,
    user: Users | None,
    origin_currency: str,
) -> dict[str, Any] | None:
    normalized_currency = str(origin_currency or "EUR").upper()
    requested_country_codes = ["BI"] if normalized_currency == "BIF" else sorted(EURO_ZONE_COUNTRY_CODES)

    if user and user.country_code:
        user_country_code = str(user.country_code).upper()
        if normalized_currency == "BIF" and user_country_code == "BI":
            requested_country_codes = ["BI"]
        elif normalized_currency != "BIF" and user_country_code in EURO_ZONE_COUNTRY_CODES:
            requested_country_codes = [user_country_code] + [
                code for code in requested_country_codes if code != user_country_code
            ]

    priority = case(
        *[(AgentAccounts.country_code == code, index) for index, code in enumerate(requested_country_codes)],
        else_=len(requested_country_codes) + 10,
    )
    row = (
        await db.execute(
            select(
                AgentAccounts.id,
                AgentAccounts.service,
                AgentAccounts.account_service,
                AgentAccounts.country_code,
                Agents.display_name,
            )
            .join(Agents, AgentAccounts.agent_id == Agents.agent_id)
            .where(
                Agents.active.is_(True),
                AgentAccounts.account_service.is_not(None),
                AgentAccounts.country_code.in_(requested_country_codes),
            )
            .order_by(priority, AgentAccounts.id.asc())
            .limit(1)
        )
    ).first()
    if not row:
        return None

    service = str(row.service or "").strip()
    account_service = str(row.account_service or "").strip()
    country_code = str(row.country_code or "").strip().upper()
    agent_name = str(row.display_name or "PesaPaid").strip()
    return {
        "id": str(row.id),
        "service": service,
        "account_service": account_service,
        "country_code": country_code,
        "agent_name": agent_name,
        "payment_currency": normalized_currency,
        "account_display": f"{service} - {account_service}" if service else account_service,
    }


def build_payment_instruction_sentence(
    *,
    amount: Decimal | str | int | float,
    currency: str,
    account_service: str,
) -> str:
    return (
        f"Veuillez envoyer un montant de {format_note_amount(amount, currency)} "
        f"vers le compte {str(account_service or '').strip()}"
    ).strip()


def build_external_transfer_payment_note_png(payload: dict[str, Any]) -> bytes:
    width = 1200
    height = 1500
    image = Image.new("RGB", (width, height), _BG_COLOR)
    draw = ImageDraw.Draw(image)
    title_font = _font(40)
    subtitle_font = _font(26)
    section_font = _font(30)
    body_font = _font(28)
    small_font = _font(22)

    draw.rounded_rectangle(
        (48, 48, width - 48, height - 48),
        radius=28,
        fill=_CARD_COLOR,
        outline=_BORDER_COLOR,
        width=2,
    )
    draw.rounded_rectangle((48, 48, width - 48, 230), radius=28, fill=_HEADER_COLOR)
    draw.text((88, 92), "PesaPaid", fill=(255, 255, 255), font=title_font)
    draw.text((88, 148), "Note de paiement", fill=(230, 238, 246), font=subtitle_font)
    draw.text((width - 360, 108), str(payload.get("reference_code") or "-"), fill=(255, 255, 255), font=section_font)

    y = 268

    def section(title: str, rows: list[tuple[str, str]]) -> None:
        nonlocal y
        draw.text((88, y), title, fill=_ACCENT_COLOR, font=section_font)
        y += 18
        for label, value in rows:
            value_lines = wrap(value or "-", width=38) or ["-"]
            row_height = max(64, 20 + (len(value_lines) * 22) + 16)
            draw.rounded_rectangle(
                (88, y + 18, width - 88, y + 18 + row_height),
                radius=18,
                fill=(249, 250, 251),
            )
            draw.text((116, y + 32), label.upper(), fill=(0, 0, 0), font=small_font)
            for index, line in enumerate(value_lines):
                draw.text((430, y + 30 + (index * 22)), line, fill=_TEXT_COLOR, font=body_font)
            y += row_height + 20
        y += 12

    section(
        "Transfert",
        [
            ("Client", str(payload.get("client_name") or "-")),
            ("Beneficiaire", str(payload.get("recipient_name") or "-")),
            ("Montant envoye", str(payload.get("sent_amount_text") or "-")),
            ("Charges", str(payload.get("fee_amount_text") or "-")),
            ("Montant a payer", str(payload.get("amount_text") or "-")),
            ("Pays destination", str(payload.get("country_destination") or "-")),
        ],
    )

    sentence = str(payload.get("payment_sentence") or "").strip()
    draw.text((88, y), "Instruction", fill=_ACCENT_COLOR, font=section_font)
    y += 28
    for line in wrap(sentence, width=48):
        draw.text((96, y), line, fill=(0, 0, 0), font=body_font)
        y += 28
    y += 10

    section(
        "Informations de paiement",
        [
            ("Service", str(payload.get("service") or "-")),
            ("Compte", str(payload.get("account_service") or "-")),
            ("Pays du compte", str(payload.get("account_country_code") or "-")),
            ("Devise de paiement", str(payload.get("payment_currency") or "-")),
        ],
    )

    footer = (
        "Veuillez effectuer le paiement exactement sur le compte indique. "
        "Conservez cette note comme reference de paiement."
    )
    for line in wrap(footer, width=68):
        draw.text((88, y), line, fill=_MUTED_COLOR, font=small_font)
        y += 24

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_external_transfer_payment_note_pdf(payload: dict[str, Any]) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    pdf.set_fill_color(11, 59, 100)
    pdf.rect(0, 0, 210, 34, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "PesaPaid - Note de paiement", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, str(payload.get("reference_code") or "-"), ln=True, align="C")
    pdf.ln(6)

    pdf.set_text_color(0, 0, 0)

    def section(title: str, rows: list[tuple[str, str]]) -> None:
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(17, 94, 155)
        pdf.cell(0, 9, title, ln=True)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(0, 0, 0)
        for label, value in rows:
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(58, 7, f"{label} :", ln=0)
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 7, str(value or "-"))
        pdf.ln(1)

    section(
        "Transfert",
        [
            ("Client", str(payload.get("client_name") or "-")),
            ("Beneficiaire", str(payload.get("recipient_name") or "-")),
            ("Montant envoye", str(payload.get("sent_amount_text") or "-")),
            ("Charges", str(payload.get("fee_amount_text") or "-")),
            ("Montant a payer", str(payload.get("amount_text") or "-")),
            ("Pays destination", str(payload.get("country_destination") or "-")),
        ],
    )

    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(17, 94, 155)
    pdf.cell(0, 9, "Instruction", ln=True)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 7, str(payload.get("payment_sentence") or "-"))
    pdf.ln(1)

    section(
        "Informations de paiement",
        [
            ("Service", str(payload.get("service") or "-")),
            ("Compte", str(payload.get("account_service") or "-")),
            ("Pays du compte", str(payload.get("account_country_code") or "-")),
            ("Devise de paiement", str(payload.get("payment_currency") or "-")),
        ],
    )

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(
        0,
        5.5,
        "Veuillez effectuer le paiement exactement sur le compte indique. "
        "Conservez cette note comme reference de paiement.",
    )

    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, bytearray):
        return bytes(pdf_output)
    if isinstance(pdf_output, str):
        return pdf_output.encode("latin-1")
    return pdf_output

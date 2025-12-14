from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from fpdf import FPDF


def _fmt_amount(value: Decimal | float | int, currency: str) -> str:
    return f"{Decimal(value):,.2f} {currency}".replace(",", " ").replace("\xa0", " ")


def build_external_transfer_receipt(payload: Mapping[str, Any]) -> bytes:
    """
    Genere un PDF de recu pour un transfert externe.
    payload attend:
      reference_code, sender_name, sender_email, sender_phone,
      recipient_name, recipient_phone, amount, currency, local_amount, local_currency,
      rate, created_at, status, partner, country.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Bandeau d'en-tete
    pdf.set_fill_color(30, 64, 175)  # indigo
    pdf.rect(0, 0, 210, 36, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "PayLink - Recu de transfert externe", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Document genere automatiquement - veuillez conserver ce recu", ln=True, align="C")
    pdf.ln(6)

    # Infos generales
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 12)
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        created_str = created_at.strftime("%d/%m/%Y %H:%M")
    else:
        created_str = str(created_at)

    info_rows = [
        ("Reference", payload.get("reference_code", "-")),
        ("Date", created_str),
        ("Statut", payload.get("status", "-")),
    ]
    pdf.set_fill_color(243, 244, 246)  # gris clair
    pdf.set_font("Helvetica", "B", 12)
    for label, value in info_rows:
        pdf.cell(55, 9, label, border=0, ln=0, fill=True)
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 9, str(value), border=0, ln=1, fill=True)
        pdf.set_font("Helvetica", "B", 12)
    pdf.ln(6)

    # Tableau detaille
    table_data = [
        ("Client (emetteur)", payload.get("sender_name", "-")),
        ("Email emetteur", payload.get("sender_email", "-")),
        ("Telephone emetteur", payload.get("sender_phone", "-")),
        ("Destinataire", payload.get("recipient_name", "-")),
        ("Telephone destinataire", payload.get("recipient_phone", "-")),
        ("Montant envoye", _fmt_amount(payload["amount"], payload["currency"])),
        ("Montant a remettre", _fmt_amount(payload["local_amount"], payload["local_currency"])),
        (
            "Taux applique",
            f"1 {payload['currency']} = {payload.get('rate', '-')} {payload['local_currency']}",
        ),
        ("Pays", payload.get("country", "-")),
        ("Partenaire", payload.get("partner", "-")),
    ]

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(30, 64, 175)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(70, 9, "Detail", border=0, ln=0, align="L", fill=True)
    pdf.cell(0, 9, "Valeur", border=0, ln=1, align="L", fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 12)
    fill_toggle = False
    for label, value in table_data:
        pdf.set_fill_color(249, 250, 251) if fill_toggle else pdf.set_fill_color(255, 255, 255)
        pdf.cell(70, 8, str(label), border=0, ln=0, fill=True)
        pdf.cell(0, 8, str(value), border=0, ln=1, fill=True)
        fill_toggle = not fill_toggle

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(
        0,
        6,
        "Ce recu atteste de la demande de transfert externe initiee depuis PayLink. "
        "Merci de conserver ce document pour vos archives.",
    )

    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, bytearray):
        return bytes(pdf_output)
    if isinstance(pdf_output, str):
        return pdf_output.encode("latin-1")
    return pdf_output

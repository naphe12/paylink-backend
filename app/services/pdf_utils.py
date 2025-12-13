from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from fpdf import FPDF


def _fmt_amount(value: Decimal | float | int, currency: str) -> str:
    return f"{Decimal(value):,.2f} {currency}".replace(",", " ").replace("\xa0", " ")


def build_external_transfer_receipt(payload: Mapping[str, Any]) -> bytes:
    """
    GÇ¸nÇ¸re un petit PDF de rÇ¸cupu pour un transfert externe.
    payload attend:
      reference_code, sender_name, sender_email, sender_phone,
      recipient_name, recipient_phone, amount, currency, local_amount, local_currency,
      rate, created_at, status, partner, country.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Reçu de transfert externe", ln=True, align="C")

    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, f"Référence : {payload['reference_code']}", ln=True)
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        created_str = created_at.strftime("%d/%m/%Y %H:%M")
    else:
        created_str = str(created_at)
    pdf.cell(0, 8, f"Date : {created_str}", ln=True)
    pdf.ln(4)

    # Emmeteur
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Client (émetteur)", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 7, f"Nom : {payload.get('sender_name', '-')}", ln=True)
    pdf.cell(0, 7, f"Email : {payload.get('sender_email', '-')}", ln=True)
    pdf.cell(0, 7, f"Téléphone : {payload.get('sender_phone', '-')}", ln=True)
    pdf.ln(3)

    # Destinataire
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Destinataire", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 7, f"Nom : {payload.get('recipient_name', '-')}", ln=True)
    pdf.cell(0, 7, f"Téléphone : {payload.get('recipient_phone', '-')}", ln=True)
    pdf.ln(3)

    # Montants
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Détails du transfert", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 7, f"Montant envoyé : {_fmt_amount(payload['amount'], payload['currency'])}", ln=True)
    pdf.cell(
        0,
        7,
        f"Montant à remettre : {_fmt_amount(payload['local_amount'], payload['local_currency'])}",
        ln=True,
    )
    if payload.get("rate"):
        pdf.cell(0, 7, f"Taux appliqué : 1 {payload['currency']} = {payload['rate']} {payload['local_currency']}", ln=True)
    pdf.cell(0, 7, f"Pays / Partenaire : {payload.get('country', '-') } / {payload.get('partner', '-')}", ln=True)
    pdf.cell(0, 7, f"Statut : {payload.get('status', '-')}", ln=True)
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        "Ce reçu atteste de la demande de transfert externe initiée depuis PayLink. "
        "Merci de conserver ce document pour vos archives.",
    )

    # Retourne les bytes de maniÇùre robuste (fpdf2 peut renvoyer bytearray ou str)
    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, bytearray):
        return bytes(pdf_output)
    if isinstance(pdf_output, str):
        return pdf_output.encode("latin-1")
    return pdf_output

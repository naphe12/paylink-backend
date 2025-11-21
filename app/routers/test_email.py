from fastapi import APIRouter
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import settings

router = APIRouter(prefix="/test", tags=["email-test"])


@router.get("/email")
def test_email():
    try:
        sender = settings.MAIL_FROM
        recipient = "adolphe.nahimana@gmail.com"  #  <<< remplace ici
        subject = "Test SMTP PayLink"
        body = "Ceci est un test SMTP envoyé depuis Railway via smtplib."

        # ---- 1️⃣ Construire le message MIME ----
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # ---- 2️⃣ Connexion SMTP ----
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()  # si port 587
        server.login(settings.SMTP_USER, settings.SMTP_PASS)

        # ---- 3️⃣ Envoi ----
        server.sendmail(sender, recipient, msg.as_string())
        server.quit()

        return {"status": "ok", "message": "Email envoyé avec succès !"}

    except Exception as e:
        return {"status": "error", "details": str(e)}


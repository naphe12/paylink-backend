from fastapi import APIRouter
from app.services.mailjet_service import MailjetEmailService

router = APIRouter(prefix="/test", tags=["email"])

@router.get("/email")
def test_mailjet():
    mailer = MailjetEmailService()
    return mailer.send_email(
        to_email="adolphe.nahimana@gmail.com",
        subject="Test Mailjet - PayLink",
        text="Ceci est un test d'envoi d'email depuis FastAPI + Railway avec Mailjet API."
    )


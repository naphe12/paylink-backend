from fastapi import APIRouter
from mailjet_rest import Client
import os
from app.core.config import settings
router = APIRouter(prefix="/testmail", tags=["email"])

@router.get("/")
def test_mailjet():
    try:
        # 🔹 Charger les clés depuis les variables d'environnement Railway
        api_key = settings.MAILJET_API_KEY
        api_secret = settings.MAILJET_SECRET_KEY

        if not api_key or not api_secret:
            return {"error": "Missing Mailjet API keys in environment variables"}

        # 🔹 Initialiser Mailjet client
        mailjet = Client(auth=(api_key, api_secret), version='v3.1')

        # 🔹 Construire le message
        data = {
            'Messages': [
                {
                    "From": {
                        "Email": "no-reply@paylink.app",
                        "Name": "PayLink"
                    },
                    "To": [
                        {
                            "Email": "adolphe.nahimana@gmail.com",   # <<< CHANGE ICI
                            "Name": "Test Recipient"
                        }
                    ],
                    "Subject": "Test Mailjet depuis PayLink",
                    "TextPart": "Ceci est un test Mailjet depuis FastAPI + Railway.",
                    "HTMLPart": "<h3>Test Mailjet réussi 🚀</h3><p>Email envoyé depuis votre backend PayLink !</p>"
                }
            ]
        }

        # 🔹 Envoyer le mail
        result = mailjet.send.create(data=data)
        return {
            "status": result.status_code,
            "response": result.json()
        }

    except Exception as e:
        return {"error": str(e)}


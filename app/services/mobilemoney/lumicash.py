import uuid
from datetime import datetime


async def send_lumicash_payment(phone: str, amount: float):
    """
    Simulation API Lumicash
    - Dans la vraie version → envoi requête HTTP à l’API Lumicash
    """
    # Simulation : 90% de chance que le paiement passe
    from random import random
    success = random() > 0.1

    tx_ref = str(uuid.uuid4())

    if success:
        return {
            "status": "success",
            "transaction_ref": tx_ref,
            "message": "Paiement Lumicash réussi ✅",
            "confirmed_at": datetime.utcnow().isoformat()
        }
    else:
        return {
            "status": "failed",
            "transaction_ref": tx_ref,
            "message": "Paiement Lumicash échoué ❌"
        }

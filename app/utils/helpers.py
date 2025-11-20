# app/utils/helpers.py
import decimal
import uuid
from datetime import datetime


def generate_uuid() -> str:
    """Génère un UUID sous forme de string."""
    return str(uuid.uuid4())

def format_amount(amount: decimal.Decimal, currency: str = "EUR") -> str:
    """Affiche joliment un montant."""
    return f"{amount:.2f} {currency}"

def format_datetime(dt: datetime) -> str:
    """Retourne une date formatée (ex: 04/11/2025 14:32)."""
    return dt.strftime("%d/%m/%Y %H:%M")

def mask_email(email: str) -> str:
    """Masque une partie de l’email pour la confidentialité."""
    parts = email.split("@")
    if len(parts) != 2:
        return email
    name, domain = parts
    return f"{name[0]}***@{domain}"

def safe_decimal(value) -> decimal.Decimal:
    """Convertit proprement une valeur en Decimal, même depuis une string."""
    try:
        return decimal.Decimal(str(value))
    except Exception:
        return decimal.Decimal("0.00")
    
def calculate_risk_score(user, stats):
    score = 0

    # 1. Age du compte
    days = (datetime.utcnow() - user.created_at).days
    if days < 7: score += 40
    elif days < 30: score += 20

    # 2. Historique régulier
    if stats.total_transactions < 3: score += 20

    # 3. Volume inhabituel ce mois
    if stats.month_volume > stats.avg_month_volume * 3:
        score += 30

    # 4. Vérification identité complète
    if user.kyc_tier == "BASIC": score += 20
    elif user.kyc_tier == "STANDARD": score += 5

    return min(score, 100)


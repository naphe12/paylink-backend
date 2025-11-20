# app/services/risk_engine.py
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from app.models.users import Users
from app.models.wallet_transactions import WalletTransactions

async def calculate_risk_score(db, user_id: str):
    # Charger informations utilisateur
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        return None

    score = 0
    now = datetime.now(timezone.utc)
    created_at = user.created_at
    if created_at:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = now

    # ----- 1) Âge du compte -----
    days = (now - created_at).days
    if days < 7:
        score += 40
    elif days < 30:
        score += 20

    # ----- 2) Activité transactionnelle -----
    q_tx_count = select(func.count()).where(WalletTransactions.user_id == user_id)
    total_tx = (await db.execute(q_tx_count)).scalar() or 0

    if total_tx < 3:
        score += 25

    # ----- 3) Volume ce mois vs historique -----
    one_month_ago = now - timedelta(days=30)

    q_month_sum = select(func.sum(WalletTransactions.amount)).where(
        WalletTransactions.user_id == user_id,
        WalletTransactions.created_at >= one_month_ago
    )
    month_volume = (await db.execute(q_month_sum)).scalar() or 0

    # Estimation simple du volume moyen historique
    avg_month_volume = month_volume / max(days / 30, 1)

    if month_volume > avg_month_volume * 3 and month_volume > 100000:
        score += 30

    # ----- 4) Niveau KYC -----
    if user.kyc_tier == "BASIC":
        score += 20
    elif user.kyc_tier == "STANDARD":
        score += 5

    score = min(score, 100)  # Cap max
    user.risk_score = score
    await db.commit()
    from app.services.security_log import log_event

    # ✅ NOUVEAU : Si le score dépasse 80 → on log & on bloque
    if score >= 80 and (user.previous_score or 0) < 80:
        await log_event(
            db,
            user_id=user.user_id,
            severity="critical",
            event_type="risk_block",
            message=f"Niveau de risque critique détecté (score={score}). Compte gelé."
        )
        user.status = "frozen"
        await db.commit()


    return score


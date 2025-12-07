# app/services/aml.py
import json
import os
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amlevents import AmlEvents
from app.models.security_events import SecurityEvents, SecuritySeverityEnum
from app.models.transactions import Transactions
from app.models.users import Users
from app.services.admin_notifications import push_admin_notification

ALERT_THRESHOLD = int(os.getenv("AML_SCORE_ALERT", 50))
FREEZE_THRESHOLD = int(os.getenv("AML_SCORE_FREEZE", 80))

async def update_risk_score(db: AsyncSession, user: Users, tx_amount: Decimal = None, channel: str = None):
    """
    Recalcule entièrement le score de risque et applique les conséquences.
    """

    score = 0

    # 1. Score basé sur niveau KYC
    tier_scores = {0: 25, 1: 15, 2: 7, 3: 2}
    score += tier_scores.get(user.kyc_tier or 0, 20)

    # 2. Historique derniers montants
    tx_list = await db.scalars(
        select(Transactions.amount)
        .where(Transactions.initiated_by == user.user_id)
        .order_by(Transactions.created_at.desc())
        .limit(20)
    )
    for amount in tx_list:
        if amount >= Decimal("300000"):
            score += 8
        if amount >= Decimal("1000000"):
            score += 18

    # 3. Plusieurs destinataires différents
    distinct_receivers_subq = (
        select(Transactions.receiver_wallet)
        .where(Transactions.initiated_by == user.user_id)
        .distinct()
    ).subquery()
    distinct_receivers = await db.scalar(
        select(func.count()).select_from(distinct_receivers_subq)
    ) or 0
    if distinct_receivers > 8:
        score += 12

    # 4. Impact immédiat si tx fourni
    if tx_amount:
        if tx_amount >= Decimal("1000000"):
            score += 15
        if channel in {"cash", "agent", "external"}:
            score += 10

    # 5. Sauvegarde score utilisateur
    old_score = user.risk_score or 0
    user.risk_score = score

    # Log AML Event (match AmlEvents schema)
    computed_risk_level = (
        "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 40 else "low"
    )
    await db.execute(insert(AmlEvents).values(
        user_id=user.user_id,
        rule_code=f"risk_update:{channel or 'none'}",
        risk_level=computed_risk_level,
        details={
            "score_delta": float(score - old_score),
            "new_score": float(score),
            "old_score": float(old_score),
            "channel": channel,
            "tx_amount": float(tx_amount) if tx_amount is not None else None,
        }
    ))

    # Log Security Event
    severity_level = (
        SecuritySeverityEnum.HIGH.value
        if score >= 80
        else SecuritySeverityEnum.MEDIUM.value
        if score >= 50
        else SecuritySeverityEnum.LOW.value
    )
    await db.execute(insert(SecurityEvents).values(
        user_id=user.user_id,
        severity=severity_level,
        event_type="risk_update",
        message = f"Risk score {old_score} → {score} (Δ={score-old_score})",
        context=json.dumps({
            "message": f"Risk score {old_score} → {score} (Δ={score-old_score})",
            "old_score": float(old_score),
            "new_score": float(score),
        }),
    ))

    # Apply Business Rules
    if score >= FREEZE_THRESHOLD:
        user.status = "frozen"
        await db.commit()
        await push_admin_notification(
            "aml_high",
            db=db,
            user_id=user.user_id,
            severity="critical",
            title="Compte gele (AML)",
            message=f"{user.full_name or user.email} bloque pour suspicion AML (score {score}).",
            metadata={
                "score": score,
                "action": "freeze",
                "channel": channel,
            },
        )
        await db.commit()
        raise HTTPException(423, "Compte gele pour enquete AML.")

    if score >= ALERT_THRESHOLD:
        await push_admin_notification(
            "aml_high",
            db=db,
            user_id=user.user_id,
            severity="warning",
            title="Alerte AML",
            message=f"Score AML eleve ({score}) pour {user.full_name or user.email}.",
            metadata={
                "score": score,
                "channel": channel,
            },
        )

    await db.commit()
    return score

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.risk_service import RiskResult

async def enqueue_alert(
    db: AsyncSession,
    *,
    type: str,
    severity: str,
    user_id: str | None,
    order_id: str | None,
    payload: dict,
):
    await db.execute(text("""
      INSERT INTO paylink.alerts(type, severity, user_id, order_id, payload)
      VALUES (:type, :severity, :user_id::uuid, :order_id::uuid, :payload::jsonb)
    """), {
        "type": type,
        "severity": severity,
        "user_id": user_id,
        "order_id": order_id,
        "payload": payload,
    })

async def log_risk_decision(
    db: AsyncSession,
    *,
    user_id: str | None,
    order_id: str | None,
    stage: str,
    result: RiskResult,
):
    await db.execute(text("""
      INSERT INTO paylink.risk_decisions (user_id, order_id, stage, decision, score, reasons)
      VALUES (:user_id::uuid, :order_id::uuid, :stage, :decision, :score, :reasons::jsonb)
    """), {
        "user_id": user_id,
        "order_id": order_id,
        "stage": stage,
        "decision": result.decision,
        "score": result.score,
        "reasons": result.reasons,
    })

    if result.score >= 80:
        await enqueue_alert(
            db,
            type="RISK_HIGH",
            severity="HIGH",
            user_id=user_id,
            order_id=order_id,
            payload={"stage": stage, "score": result.score, "reasons": result.reasons},
        )
